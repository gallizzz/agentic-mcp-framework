"""Formal Gate Node for LangGraph.

LangGraph node for runtime action sanitisation via AsmetaS MCP server.
"""

import json
import logging
import re
from typing import Any, Callable, Dict, Literal, Optional, Tuple
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field, ValidationError
from agent.agent_state import AgentState
logger = logging.getLogger("formal_gate")

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
  parts = snake_str.split("_")
  return parts[0] + "".join(p.capitalize() for p in parts[1:])

def _extract_candidate_action(
    state: AgentState, last_msg: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  """Extracts proposed candidate action and tool_call_id from state or last message."""
  candidate = state.get("candidate_action")
  tool_call_id = None

  if last_msg and getattr(last_msg, "tool_calls", None):
    tc = last_msg.tool_calls[0]
    candidate = {
        "name": tc["name"],
        "args": dict(tc.get("args") or {}),
        "id": tc.get("id"),
    }
    tool_call_id = tc.get("id")

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
  monitored_vars = {}

  # Primary action resolution
  action_val = next(
      (
          str(tool_args[k])
          for k in ("inputAction", "action", "command", "operation")
          if k in tool_args
      ),
      "IDLE",
  )
  monitored_vars["inputAction"] = action_val

  # Primitive tool args & camelCase conversion
  for k, v in tool_args.items():
    if k not in ("action", "command", "operation") and isinstance(
        v, (str, int, float, bool)
    ):
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
      for var_name, var_val in re.findall(
          r"(\b[a-zA-Z_]\w*)\s*[:=]\s*([a-zA-Z0-9_\.-]+)", content
      ):
        if var_name not in monitored_vars and var_name not in ("id", "type"):
          monitored_vars[var_name] = var_val

  # Defaults and action mapping
  for k, v in default_vars.items():
    monitored_vars.setdefault(k, str(v))

  act = monitored_vars.get("inputAction")
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
    if hasattr(callable_obj, "ainvoke"):
      res = await callable_obj.ainvoke({"monitored_variables": monitored_vars})
    elif hasattr(callable_obj, "invoke"):
      res = callable_obj.invoke({"monitored_variables": monitored_vars})
    else:
      res = (
          await callable_obj(monitored_vars)
          if hasattr(callable_obj(monitored_vars), "__await__")
          else callable_obj(monitored_vars)
      )

    if isinstance(res, list) and res:
      res = res[0].get("text", "") if isinstance(res[0], dict) else res[0]

    res_data = json.loads(res) if isinstance(res, str) else res
    if not isinstance(res_data, dict):
      return "ERROR", None, f"Unexpected response type: {type(res_data)}", {}

    if res_data.get("status") == "error":
      return (
          "ERROR",
          None,
          res_data.get("message", "Error reported by AsmetaS."),
          {},
      )

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

# ============================================================================
# FORMAL GATE NODE CLASS
# ============================================================================

class FormalGateNode:
  """Deterministic gate for runtime action sanitisation via AsmetaS."""

  def __init__(
      self,
      default_safe_action: str,
      sanitise_action_callable: Optional[Callable] = None,
      policy: Literal["shielding", "replan"] = "shielding",
      error_policy: Literal["fail_stop", "fail_safe"] = "fail_safe",
      monitored_tools: Optional[list[str]] = None,
      action_mapping: Optional[Dict[str, str]] = None,
      default_monitored_vars: Optional[Dict[str, str]] = None,
  ):
    self.sanitise_action_callable = sanitise_action_callable
    self.policy = policy
    self.error_policy = error_policy
    self.default_safe_action = default_safe_action
    self.monitored_tools = monitored_tools
    self.action_mapping = dict(action_mapping or {})
    self.default_monitored_vars = dict(default_monitored_vars or {})

  def _is_actuator_action(
      self, tool_name: str, tool_args: dict
  ) -> Tuple[bool, str]:
    """Filters read-only tools from actuation commands."""
    if self.monitored_tools is not None:
      return (
          (True, "")
          if tool_name in self.monitored_tools
          else (False, f"Tool '{tool_name}' unmonitored.")
      )

    read_prefixes = (
        "get_",
        "read_",
        "list_",
        "query_",
        "fetch_",
        "status_",
        "show_",
        "check_",
    )
    read_suffixes = (
        "_telemetry",
        "_status",
        "_info",
        "_state",
        "_reading",
        "_readings",
    )

    if tool_name.startswith(read_prefixes) or tool_name.endswith(read_suffixes):
      return False, f"Tool '{tool_name}' is perception/read-only."

    if not any(
        k in tool_args
        for k in ("inputAction", "action", "command", "operation")
    ):
      return False, f"Tool '{tool_name}' has no actuator command."

    return True, ""

  async def __call__(self, state: AgentState) -> Dict[str, Any]:
    messages = list(state.get("messages", []))
    last_msg = messages[-1] if messages else None
    action_history = list(state.get("action_history", []))

    # Resolve Candidate Action
    candidate_action, tool_call_id = _extract_candidate_action(state, last_msg)
    if not candidate_action:
      return {
          "guard_verdict": "BYPASS",
          "guard_feedback": "No action proposed.",
          "candidate_action": None,
          "sanitised_action": None,
      }

    tool_name = candidate_action.get("name", "")
    tool_args = candidate_action.get("args", {})

    # Read-only filter check (BYPASS)
    is_actuator, bypass_reason = self._is_actuator_action(tool_name, tool_args)
    if not is_actuator:
      return {
          "guard_verdict": "BYPASS",
          "guard_feedback": bypass_reason,
          "candidate_action": candidate_action,
          "sanitised_action": candidate_action,
      }

    # Monitored Variables Extraction & AsmetaS Invocation
    monitored_vars = _extract_monitored_variables(
        tool_args, messages, self.default_monitored_vars, self.action_mapping
    )

    verdict, sanitised_val, feedback, raw_output = (
        await _invoke_sanitise_callable(
            self.sanitise_action_callable, monitored_vars
        )
    )

    # Reverse action alias mapping
    if sanitised_val and self.action_mapping:
      rev_map = {v: k for k, v in self.action_mapping.items()}
      sanitised_val = rev_map.get(sanitised_val, sanitised_val)

    # Handle Errors & Fail-Safe Policy
    if verdict == "ERROR":
      if self.error_policy == "fail_safe":
        verdict = "VIOLATION"
        sanitised_val = self.default_safe_action
        feedback = f"Enforcer error ({feedback}). Fail-safe applied: '{self.default_safe_action}'."
      else:
        action_history.append({
            "proposed_action": candidate_action,
            "monitored_variables": monitored_vars,
            "verdict": "ERROR",
            "feedback": feedback,
        })
        return {
            "guard_verdict": "ERROR",
            "guard_feedback": feedback,
            "candidate_action": candidate_action,
            "sanitised_action": None,
            "action_history": action_history,
            "messages": [
                ToolMessage(
                    content=f"[Formal Gate Error] {feedback}",
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        }

    # Build Sanitised Action & Record History
    sanitised_args = dict(tool_args)
    target_key = next(
        (k for k in ("inputAction", "action") if k in sanitised_args),
        "inputAction",
    )
    sanitised_args[target_key] = (
        sanitised_val if verdict == "VIOLATION" else tool_args.get(target_key)
    )

    sanitised_action = {
        "name": tool_name,
        "args": sanitised_args,
        "id": tool_call_id,
    }

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
      return {
          "guard_verdict": "APPROVED",
          "guard_feedback": feedback,
          "candidate_action": candidate_action,
          "sanitised_action": dict(candidate_action),
          "action_history": action_history,
      }

    if verdict == "VIOLATION":
      if self.policy == "replan":
        return {
            "guard_verdict": "VIOLATION",
            "guard_feedback": feedback,
            "candidate_action": candidate_action,
            "sanitised_action": sanitised_action,
            "action_history": action_history,
            "retry_count": state.get("retry_count", 0) + 1,
            "messages": [
                ToolMessage(
                    content=(
                        "[Formal Gate Rejection] Action violates safety"
                        f" invariants. Feedback: {feedback}."
                    ),
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        }

      # Shielding mode: inline replacement of tool call arguments
      if last_msg and getattr(last_msg, "tool_calls", None):
        for tc in last_msg.tool_calls:
          if tc.get("id") == tool_call_id:
            tc["args"] = sanitised_args

      return {
          "guard_verdict": "VIOLATION",
          "guard_feedback": feedback,
          "candidate_action": candidate_action,
          "sanitised_action": sanitised_action,
          "action_history": action_history,
          "messages": [],
      }

    return {
        "guard_verdict": "BYPASS",
        "guard_feedback": feedback or "Bypassed.",
        "candidate_action": candidate_action,
        "sanitised_action": candidate_action,
        "action_history": action_history,
    }