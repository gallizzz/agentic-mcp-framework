"""Formal Gate Node for LangGraph.

LangGraph node for runtime action sanitisation via AsmetaS MCP server.
"""

import copy
import json
import re
from typing import Any, Awaitable, Callable, Dict, Literal, Optional, Set, Tuple
import uuid
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ValidationError
from core.agent_state import AgentState
from core.environment_node import APPROVED_NOTICE, _shielding_notice
from core.mcp_utils import mcp_result_text, parse_mcp_response

# Submit mode: async callable (tool args) -> (is_error, raw text result) bound to the MCP session
SubmitCallable = Callable[[Dict[str, Any]], Awaitable[Tuple[bool, str]]]

REPLAN_NOTICE = "[FORMAL GATE: REPLAN] Nessuna modifica è stata applicata."
BLOCKED_NOTICE = "[FORMAL GATE: BLOCKED] Azione bloccata dall'enforcer formale."

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

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _to_camel_case(snake_str: str) -> str:
    """Converts snake_case to camelCase."""
    if "_" not in snake_str:
        return snake_str
    first, *rest = snake_str.split("_")
    return first + "".join(p.capitalize() for p in rest)

def _extract_candidate_action(last_msg: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Returns the first tool call of the Planner message (the router only sends tool calls here)."""
    tc = last_msg.tool_calls[0]
    tool_call_id = tc.get("id")
    return {"name": tc["name"], "args": dict(tc.get("args") or {}), "id": tool_call_id}, tool_call_id

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
) -> Tuple[str, Optional[str], str]:
    """Invokes AsmetaS sanitise_action MCP tool and validates response structure."""
    try:
        res = await callable_obj.ainvoke({"monitored_variables": monitored_vars})
        if isinstance(res, list):
            res = mcp_result_text(res)

        res_data = json.loads(res) if isinstance(res, str) else res
        if not isinstance(res_data, dict):
            return "ERROR", None, f"Unexpected response type: {type(res_data)}"

        if res_data.get("status") == "error":
            return "ERROR", None, res_data.get("message", "Error reported by AsmetaS.")

        validated = SanitiseResult.model_validate(res_data)
        return validated.verdict, validated.sanitised_action, validated.feedback

    except ValidationError as val_err:
        err_msg = val_err.errors()[0]["msg"] if val_err.errors() else str(val_err)
        return "ERROR", None, f"Sanitise response schema error: {err_msg}"
    except Exception as e:
        return "ERROR", None, f"Enforcer exception: {str(e)}"

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

def _set_path(args: Dict[str, Any], dotted_path: str, value: Any) -> None:
    """Sets args[a][b]... = value when every intermediate key holds a dict."""
    *parents, leaf = dotted_path.split(".")
    target = args
    for key in parents:
        target = target.get(key)
        if not isinstance(target, dict):
            return
    target[leaf] = value

def _compact_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Result shown to the Planner: drops per-step preview evidence, keeps its outcome."""
    compact = dict(result)
    preview = compact.get("preview")
    if isinstance(preview, dict):
        compact["preview"] = {"outcome": preview.get("outcome")}
    return compact

def _skip_extra_tool_calls(last_msg: Any) -> list:
    """Answers every tool call after the first one without executing it (one gated action per response)."""
    return [
        ToolMessage(
            content="[Formal Gate] Not executed: only one action per response is evaluated"
                    " by the Formal Gate. Propose it again if still needed.",
            tool_call_id=tc.get("id"),
            status="error",
        )
        for tc in last_msg.tool_calls[1:]
    ]

# ============================================================================
# FORMAL GATE NODE CLASS
# ============================================================================

class FormalGateNode:
    """Deterministic gate for runtime action verification via AsmetaS.

    Fail-closed: every tool call is gated unless the tool is declared read-only.
    - "sanitise" mode: asks AsmetaS for a verdict; the Environment executes the action.
    - "submit" mode: calls the use case's submit tool, which verifies and executes the
      action itself; the returned decision is mapped to a verdict via decision_mapping.
    """

    def __init__(
        self,
        default_safe_action: Optional[str] = None,
        sanitise_action_callable: Optional[Callable] = None,
        policy: Literal["shielding", "replan"] = "shielding",
        error_policy: Literal["fail_stop", "fail_safe"] = "fail_safe",
        read_only_tools: Optional[Set[str]] = None,
        action_mapping: Optional[Dict[str, str]] = None,
        default_monitored_vars: Optional[Dict[str, str]] = None,
        gate_mode: Literal["sanitise", "submit"] = "sanitise",
        submit_callable: Optional[SubmitCallable] = None,
        submit_tool: Optional[str] = None,
        submit_request_id_path: Optional[str] = None,
        decision_mapping: Optional[Dict[str, str]] = None,
    ):
        self.gate_mode = gate_mode
        self.submit_callable = submit_callable
        self.submit_tool = submit_tool
        self.submit_request_id_path = submit_request_id_path
        self.decision_mapping = dict(decision_mapping or {})
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
    ) -> Dict[str, Any]:
        """Rejects the action and terminates the turn without touching the environment."""
        return _gate_result(
            "ERROR", feedback, candidate_action, None,
            messages=[
                ToolMessage(
                    content=f"[Formal Gate Error] {feedback}",
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        )

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        result = await self._evaluate(state)
        skipped_messages = _skip_extra_tool_calls(state["messages"][-1])
        if skipped_messages:
            result["messages"] = list(result.get("messages") or []) + skipped_messages
        return result

    async def _evaluate(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        last_msg = messages[-1]

        # Resolve Candidate Action
        candidate_action, tool_call_id = _extract_candidate_action(last_msg)

        tool_name = candidate_action.get("name", "")
        tool_args = candidate_action.get("args", {})

        # Only tools explicitly declared read-only skip formal verification
        if tool_name in self.read_only_tools:
            return _gate_result(
                "BYPASS", f"Tool '{tool_name}' is declared read-only.",
                candidate_action, candidate_action,
            )

        if self.gate_mode == "submit":
            return await self._evaluate_submit(candidate_action, tool_call_id)

        # Fail-closed: an actuator call the ASM cannot evaluate is never executed
        if not any(k in tool_args for k in ACTION_ARG_KEYS):
            return self._block(
                f"Tool '{tool_name}' is not read-only and has no action argument"
                f" ({', '.join(ACTION_ARG_KEYS)}) to verify against the ASM.",
                candidate_action, tool_call_id,
            )

        # Monitored Variables Extraction & AsmetaS Invocation
        monitored_vars = _extract_monitored_variables(
            tool_args, messages, self.default_monitored_vars, self.action_mapping
        )
        verdict, sanitised_val, feedback = await _invoke_sanitise_callable(
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
                return self._block(feedback, candidate_action, tool_call_id)

        # Build Sanitised Action
        sanitised_args = dict(tool_args)
        target_key = next(
            (k for k in ("inputAction", "action") if k in sanitised_args), "inputAction"
        )
        sanitised_args[target_key] = (
            sanitised_val if verdict == "VIOLATION" else tool_args.get(target_key)
        )
        sanitised_action = {"name": tool_name, "args": sanitised_args, "id": tool_call_id}

        # Apply Policy
        if verdict == "APPROVED":
            return _gate_result("APPROVED", feedback, candidate_action, dict(candidate_action))

        if self.policy == "replan":
            return _gate_result(
                "VIOLATION", feedback, candidate_action, sanitised_action,
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
        for tc in last_msg.tool_calls:
            if tc.get("id") == tool_call_id:
                tc["args"] = sanitised_args

        return _gate_result(
            "VIOLATION", feedback, candidate_action, sanitised_action,
            messages=[],
        )

    async def _evaluate_submit(
        self,
        candidate_action: Dict[str, Any],
        tool_call_id: Optional[str],
    ) -> Dict[str, Any]:
        """Submit mode: the enforcement server verifies AND executes; map its decision."""
        tool_name = candidate_action.get("name", "")
        if tool_name != self.submit_tool:
            return self._block(
                f"Tool '{tool_name}' is neither read-only nor the submit tool '{self.submit_tool}'.",
                candidate_action, tool_call_id,
            )

        args = copy.deepcopy(candidate_action.get("args") or {})
        if self.submit_request_id_path:
            # A fresh ID per submission: the LLM never chooses or reuses it
            _set_path(args, self.submit_request_id_path, f"req-{uuid.uuid4().hex[:12]}")
        submitted = {"name": tool_name, "args": args, "id": tool_call_id}

        try:
            is_error, raw = await self.submit_callable(args)
        except Exception as e:
            return self._block(f"Enforcement server unreachable: {e}", submitted, tool_call_id)

        result, _ = parse_mcp_response(raw)
        if is_error or result.get("status") == "invalid_request":
            # Rejected before reaching the ASM models (schema or binding validation)
            reason = result.get("reason") or raw
            return self._submit_result(
                "REPLAN", f"Request rejected before the ASM models: {reason}",
                submitted, result, tool_call_id,
            )
        if result.get("status") != "completed":
            return self._block(
                f"Enforcement server error ({result.get('status', 'no status')}):"
                f" {result.get('reason', raw)}",
                submitted, tool_call_id,
            )

        decision = result.get("decision")
        verdict = self.decision_mapping.get(decision)
        if verdict is None:
            return self._block(f"Unmapped enforcement decision '{decision}'.", submitted, tool_call_id)
        return self._submit_result(
            verdict, f"{decision}: {result.get('reason')}",
            submitted, result, tool_call_id,
        )

    @staticmethod
    def _submit_result(
        verdict: str,
        feedback: str,
        submitted: Dict[str, Any],
        result: Dict[str, Any],
        tool_call_id: Optional[str],
    ) -> Dict[str, Any]:
        """Builds the gate update and the ToolMessage the Planner reads for a submit outcome."""
        result_text = json.dumps(_compact_result(result), ensure_ascii=False)
        executed = submitted
        if verdict == "SHIELDED":
            executed = {**submitted, "args": result.get("applied_action")}
            content = _shielding_notice(submitted, executed, feedback, result_text)
        elif verdict == "APPROVED":
            content = f"{APPROVED_NOTICE}\n{result_text}"
        elif verdict == "REPLAN":
            content = f"{REPLAN_NOTICE} Motivo: {feedback}\n{result_text}"
        else:
            content = f"{BLOCKED_NOTICE} Motivo: {feedback}\n{result_text}"

        return _gate_result(
            verdict, feedback, submitted, executed,
            final_answer_only=verdict == "BLOCKED",
            messages=[
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                    status="success" if verdict in ("APPROVED", "SHIELDED") else "error",
                )
            ],
        )
