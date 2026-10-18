"""Formal Gate Node for LangGraph.

LangGraph node for runtime action sanitisation via AsmetaS MCP server.
"""

import json
import re
from typing import Any, Callable, Dict, Literal, Optional, Set, Tuple
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field, ValidationError
from core.agent_state import AgentState
from core.mcp_utils import mcp_result_text

# Tool argument names that may carry the actuator command (in priority order)
ACTION_ARG_KEYS = ("inputAction", "action", "command", "operation")
# Command aliases that are folded into `inputAction` instead of being forwarded verbatim
ACTION_ALIAS_KEYS = ("action", "command", "operation")

# Matches `var=val` / `var: val` hints inside conversation messages
_VAR_ASSIGNMENT_RE = re.compile(r"(\b[a-zA-Z_]\w*)\s*[:=]\s*([a-zA-Z0-9_\.-]+)")

# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class SanitiseResult(BaseModel):
    """Validation schema for AsmetaS sanitise_action tool response."""
    verdict: Literal["APPROVED", "VIOLATION", "ERROR"]
    input_action: Optional[str] = None
    sanitised_action: Optional[str] = None
    feedback: str = ""
    raw_output: Optional[Dict[str, Any]] = Field(default_factory=dict)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _to_camel_case(snake_str: str) -> str:
    """Converts snake_case to camelCase."""
    if "_" not in snake_str:
        return snake_str
    first, *rest = snake_str.split("_")
    return first + "".join(p.capitalize() for p in rest)

def _extract_candidate_action(
    state: AgentState, last_msg: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extracts proposed candidate action and tool_call_id from state or last message."""
    candidate = state.get("candidate_action")
    tool_call_id = None

    if last_msg and getattr(last_msg, "tool_calls", None):
        tc = last_msg.tool_calls[0]
        tool_call_id = tc.get("id")
        candidate = {
            "name": tc["name"],
            "args": dict(tc.get("args") or {}),
            "id": tool_call_id,
        }

    if candidate:
        tool_call_id = tool_call_id or candidate.get("id", "call_default")

    return candidate, tool_call_id

def _extract_monitored_variables(
    tool_args: dict,
    messages: list,
    default_vars: dict,
    action_mapping: dict,
) -> dict:
    """Extracts, normalises (snake -> camelCase), and resolves default variables."""
    # Primary action resolution (callers guarantee at least one ACTION_ARG_KEYS entry)
    action_val = next(str(tool_args[k]) for k in ACTION_ARG_KEYS if k in tool_args)
    monitored_vars = {"inputAction": action_val}

    # Primitive tool args & camelCase conversion
    for k, v in tool_args.items():
        if k not in ACTION_ALIAS_KEYS and isinstance(v, (str, int, float, bool)):
            monitored_vars[k] = str(v).lower() if isinstance(v, bool) else str(v)

    camel_vars = {
        _to_camel_case(k): v
        for k, v in monitored_vars.items()
        if _to_camel_case(k) not in monitored_vars
    }
    monitored_vars.update(camel_vars)

    # Fallback prompt parsing (var=val)
    for m in reversed(messages):
        content = getattr(m, "content", "")
        if isinstance(content, str):
            for var_name, var_val in _VAR_ASSIGNMENT_RE.findall(content):
                if var_name not in monitored_vars and var_name not in ("id", "type"):
                    monitored_vars[var_name] = var_val

    # Defaults and action mapping
    for k, v in default_vars.items():
        monitored_vars.setdefault(k, str(v))

    act = monitored_vars["inputAction"]
    if act in action_mapping:
        monitored_vars["inputAction"] = action_mapping[act]

    return monitored_vars

async def _invoke_sanitise_callable(
    callable_obj: Any, monitored_vars: dict
) -> Tuple[str, Optional[str], str, dict]:
    """Invokes AsmetaS sanitise_action MCP tool and validates response structure."""
    if callable_obj is None:
        return (
            "BYPASS",
            monitored_vars.get("inputAction"),
            "Passthrough mode (no enforcer).",
            {},
        )

    try:
        res = await callable_obj.ainvoke({"monitored_variables": monitored_vars})
        if isinstance(res, list):
            res = mcp_result_text(res)

        res_data = json.loads(res) if isinstance(res, str) else res
        if not isinstance(res_data, dict):
            return "ERROR", None, f"Unexpected response type: {type(res_data)}", {}

        if res_data.get("status") == "error":
            return "ERROR", None, res_data.get("message", "Error reported by AsmetaS."), {}

        validated = SanitiseResult.model_validate(res_data)
        return (
            validated.verdict,
            validated.sanitised_action,
            validated.feedback,
            validated.raw_output or {},
        )

    except ValidationError as val_err:
        err_msg = val_err.errors()[0]["msg"] if val_err.errors() else str(val_err)
        return "ERROR", None, f"Sanitise response schema error: {err_msg}", {}
    except Exception as e:
        return "ERROR", None, f"Enforcer exception: {str(e)}", {}

def _gate_result(
    verdict: str,
    feedback: Optional[str],
    candidate_action: Optional[Dict[str, Any]],
    sanitised_action: Optional[Dict[str, Any]],
    **extra: Any,
) -> Dict[str, Any]:
    """Builds the state update emitted by the Formal Gate."""
    return {
        "guard_verdict": verdict,
        "guard_feedback": feedback,
        "candidate_action": candidate_action,
        "sanitised_action": sanitised_action,
        **extra,
    }

# ============================================================================
# FORMAL GATE NODE CLASS
# ============================================================================

class FormalGateNode:
    """Deterministic gate for runtime action sanitisation via AsmetaS.

    Fail-closed: every tool call is gated unless the tool is declared read-only.
    """

    def __init__(
        self,
        default_safe_action: str,
        sanitise_action_callable: Optional[Callable] = None,
        policy: Literal["shielding", "replan"] = "shielding",
        error_policy: Literal["fail_stop", "fail_safe"] = "fail_safe",
        read_only_tools: Optional[Set[str]] = None,
        action_mapping: Optional[Dict[str, str]] = None,
        default_monitored_vars: Optional[Dict[str, str]] = None,
    ):
        self.sanitise_action_callable = sanitise_action_callable
        self.policy = policy
        self.error_policy = error_policy
        self.default_safe_action = default_safe_action
        self.read_only_tools = set(read_only_tools or ())
        self.action_mapping = dict(action_mapping or {})
        self.reverse_action_mapping = {v: k for k, v in self.action_mapping.items()}
        self.default_monitored_vars = dict(default_monitored_vars or {})

    @staticmethod
    def _block(
        feedback: str,
        candidate_action: Dict[str, Any],
        tool_call_id: Optional[str],
        action_history: list,
        monitored_vars: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Rejects the action and terminates the turn without touching the environment."""
        action_history.append({
            "proposed_action": candidate_action,
            "monitored_variables": monitored_vars or {},
            "verdict": "ERROR",
            "feedback": feedback,
        })
        return _gate_result(
            "ERROR", feedback, candidate_action, None,
            action_history=action_history,
            messages=[
                ToolMessage(
                    content=f"[Formal Gate Error] {feedback}",
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        )

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        last_msg = messages[-1] if messages else None
        action_history = list(state.get("action_history", []))

        # Resolve Candidate Action
        candidate_action, tool_call_id = _extract_candidate_action(state, last_msg)
        if not candidate_action:
            return _gate_result("BYPASS", "No action proposed.", None, None)

        tool_name = candidate_action.get("name", "")
        tool_args = candidate_action.get("args", {})

        # Only tools explicitly declared read-only skip formal verification
        if tool_name in self.read_only_tools:
            return _gate_result(
                "BYPASS", f"Tool '{tool_name}' is declared read-only.",
                candidate_action, candidate_action,
            )

        # Fail-closed: an actuator call the ASM cannot evaluate is never executed
        if not any(k in tool_args for k in ACTION_ARG_KEYS):
            return self._block(
                f"Tool '{tool_name}' is not read-only and has no action argument"
                f" ({', '.join(ACTION_ARG_KEYS)}) to verify against the ASM.",
                candidate_action, tool_call_id, action_history,
            )

        # Monitored Variables Extraction & AsmetaS Invocation
        monitored_vars = _extract_monitored_variables(
            tool_args, messages, self.default_monitored_vars, self.action_mapping
        )
        verdict, sanitised_val, feedback, raw_output = await _invoke_sanitise_callable(
            self.sanitise_action_callable, monitored_vars
        )

        # Reverse action alias mapping
        if sanitised_val:
            sanitised_val = self.reverse_action_mapping.get(sanitised_val, sanitised_val)

        # Handle Errors & Fail-Safe Policy
        if verdict == "ERROR":
            if self.error_policy == "fail_safe":
                verdict = "VIOLATION"
                sanitised_val = self.default_safe_action
                feedback = f"Enforcer error ({feedback}). Fail-safe applied: '{self.default_safe_action}'."
            else:
                return self._block(
                    feedback, candidate_action, tool_call_id, action_history, monitored_vars
                )

        # Build Sanitised Action & Record History
        sanitised_args = dict(tool_args)
        target_key = next(
            (k for k in ("inputAction", "action") if k in sanitised_args), "inputAction"
        )
        sanitised_args[target_key] = (
            sanitised_val if verdict == "VIOLATION" else tool_args.get(target_key)
        )
        sanitised_action = {"name": tool_name, "args": sanitised_args, "id": tool_call_id}

        action_history.append({
            "proposed_action": candidate_action,
            "monitored_variables": monitored_vars,
            "verdict": verdict,
            "sanitised_action": sanitised_action,
            "feedback": feedback,
            "raw_output": raw_output,
        })

        # Apply Policy
        if verdict == "APPROVED":
            return _gate_result(
                "APPROVED", feedback, candidate_action, dict(candidate_action),
                action_history=action_history,
            )

        if verdict == "VIOLATION":
            if self.policy == "replan":
                return _gate_result(
                    "VIOLATION", feedback, candidate_action, sanitised_action,
                    action_history=action_history,
                    retry_count=state.get("retry_count", 0) + 1,
                    messages=[
                        ToolMessage(
                            content=(
                                "[Formal Gate Rejection] Action violates safety"
                                f" invariants. Feedback: {feedback}."
                            ),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                )

            # Shielding mode: inline replacement of tool call arguments
            for tc in getattr(last_msg, "tool_calls", None) or []:
                if tc.get("id") == tool_call_id:
                    tc["args"] = sanitised_args

            return _gate_result(
                "VIOLATION", feedback, candidate_action, sanitised_action,
                action_history=action_history,
                messages=[],
            )

        return _gate_result(
            "BYPASS", feedback or "Bypassed.", candidate_action, candidate_action,
            action_history=action_history,
        )
