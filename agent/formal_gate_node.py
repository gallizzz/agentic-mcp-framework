"""
Formal Gate Node for LangGraph.
Intercepts proposed actions, communicates with the AsmetaS MCP server,
and enforces runtime formal verification and action sanitisation.
"""
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, Literal, Optional
from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from agent.agent_card import AgentCard, SanitiseContractResult
from agent.agent_state import AgentState

logger = logging.getLogger("formal_gate")


class FormalGateNode:
    """
    Deterministic gate that intercepts candidate actions, evaluates them
    against AsmetaS formal ASM specifications, and applies shielding or feedback.
    Enforces A2A contracts based on AgentCard specifications.
    """

    def __init__(
        self,
        sanitise_action_callable: Optional[Callable] = None,
        policy: Literal["shielding", "replan"] = "shielding",
        error_policy: Literal["fail_stop", "fail_safe"] = "fail_stop",
        default_safe_action: str = "STOP",
        monitored_tools: Optional[list[str]] = None,
        agent_card: Optional[AgentCard] = None,
        action_mapping: Optional[Dict[str, str]] = None,
        default_monitored_vars: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            sanitise_action_callable: Async or sync callable to invoke AsmetaS sanitise_action.
                                      Can be the LangChain StructuredTool or a direct function.
            policy: 'shielding' (sanitise action and proceed) or 'replan' (feedback to LLM).
            error_policy: 'fail_stop' (abort on error) or 'fail_safe' (force default safe action).
            default_safe_action: Fallback action when fail_safe is active.
            monitored_tools: List of tool names to intercept. If None, intercepts any action with 'inputAction'
                             or all tool calls.
            agent_card: Optional AgentCard contract specification for runtime schema validation.
            action_mapping: Optional mapping between environment action names and formal model actions (e.g. {'KEEP': 'IDLE'}).
            default_monitored_vars: Optional default values for formal model monitored variables.
        """
        self.sanitise_action_callable = sanitise_action_callable
        self.policy = policy
        self.error_policy = error_policy
        self.default_safe_action = default_safe_action
        self.monitored_tools = monitored_tools
        self.agent_card = agent_card
        self.action_mapping = dict(action_mapping or {})
        self.default_monitored_vars = dict(default_monitored_vars or {})

    def _is_actuator_action(self, tool_name: str, tool_args: dict) -> tuple[bool, str]:
        """
        Determines whether a tool invocation is an actuator action that must be guarded,
        or a perception/read-only query that can bypass the formal gate.
        """
        if self.monitored_tools is not None:
            if tool_name in self.monitored_tools:
                return True, ""
            return False, f"Tool '{tool_name}' is not in monitored tools list."

        # Read-only query / sensor naming patterns
        read_prefixes = ("get_", "read_", "list_", "query_", "fetch_", "status_", "show_", "check_", "inspect_", "describe_")
        read_suffixes = ("_telemetry", "_status", "_info", "_state", "_reading", "_readings")
        if tool_name.startswith(read_prefixes) or tool_name.endswith(read_suffixes):
            return False, f"Tool '{tool_name}' is a perception/read-only query tool."

        # Check if tool invocation includes explicit action parameters
        action_param_keys = ("inputAction", "action", "command", "operation")
        has_action_arg = any(k in tool_args for k in action_param_keys)
        if not has_action_arg:
            return False, f"Tool '{tool_name}' has no actuator command parameter."

        return True, ""

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Node execution function compatible with LangGraph.
        """
        messages = list(state.get("messages", []))
        last_message = messages[-1] if messages else None

        candidate_action = state.get("candidate_action")
        monitored_vars = dict(state.get("monitored_variables") or {})
        tool_call_id = None

        # 1. Extract action from latest AIMessage tool_calls or candidate_action in state
        if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
            first_tc = last_message.tool_calls[0]
            candidate_action = {
                "name": first_tc["name"],
                "args": dict(first_tc.get("args") or {}),
                "id": first_tc.get("id"),
            }
            tool_call_id = first_tc.get("id")

        if not candidate_action:
            # No action proposed (pure conversational turn)
            return {
                "guard_verdict": "BYPASS",
                "guard_feedback": "No candidate action proposed for evaluation.",
                "candidate_action": None,
                "sanitised_action": None,
            }

        tool_name = candidate_action.get("name", "")
        tool_args = candidate_action.get("args", {})
        if not tool_call_id:
            tool_call_id = candidate_action.get("id", "call_default")

        # Check if this tool is exempted from formal monitoring or is a read-only query
        is_actuator, bypass_reason = self._is_actuator_action(tool_name, tool_args)
        if not is_actuator:
            return {
                "guard_verdict": "BYPASS",
                "guard_feedback": bypass_reason,
                "candidate_action": candidate_action,
                "sanitised_action": candidate_action,
            }

        # 2. Extract candidate action value generically
        candidate_action_val = None
        for action_key in ("inputAction", "action", "command", "operation"):
            if action_key in tool_args:
                candidate_action_val = str(tool_args[action_key])
                break
        if not candidate_action_val:
            candidate_action_val = tool_name

        monitored_vars["inputAction"] = candidate_action_val

        # Add all arguments from tool_args into monitored_vars generically
        for k, v in tool_args.items():
            if k not in ("action", "command", "operation") and isinstance(v, (str, int, float, bool)):
                monitored_vars[k] = str(v).lower() if isinstance(v, bool) else str(v)

        # Normalize snake_case keys to camelCase (e.g. right_lane_free -> rightLaneFree)
        normalized_keys = {}
        for k, v in list(monitored_vars.items()):
            if "_" in k:
                camel_k = "".join(part.capitalize() if i > 0 else part for i, part in enumerate(k.split("_")))
                normalized_keys[camel_k] = v
        for k, v in normalized_keys.items():
            if k not in monitored_vars:
                monitored_vars[k] = v

        # Parameter extraction from conversational context:
        # Matches generic patterns like var=value or var: value (e.g. doorOpen=false, light=on, temp=20)
        for m in reversed(messages):
            content = getattr(m, "content", "")
            if isinstance(content, str):
                matches = re.findall(r'(\b[a-zA-Z_]\w*)\s*[:=]\s*([a-zA-Z0-9_\.-]+)', content)
                for var_name, var_val in matches:
                    if var_name not in monitored_vars and var_name not in ("id", "type"):
                        monitored_vars[var_name] = var_val

        # 3. Populate default monitored variables as fallbacks if still undefined
        for k, v in self.default_monitored_vars.items():
            if k not in monitored_vars:
                monitored_vars[k] = str(v)

        # Apply action mapping if configured (e.g. KEEP -> IDLE)
        original_action = monitored_vars.get("inputAction")
        if original_action in self.action_mapping:
            monitored_vars["inputAction"] = self.action_mapping[original_action]

        # 3. Call AsmetaS sanitise_action
        verdict = "ERROR"
        sanitised_val = None
        feedback = ""
        raw_output = {}

        try:
            if self.sanitise_action_callable is not None:
                # Invoke the tool
                if hasattr(self.sanitise_action_callable, "ainvoke"):
                    res = await self.sanitise_action_callable.ainvoke({"monitored_variables": monitored_vars})
                elif hasattr(self.sanitise_action_callable, "invoke"):
                    res = self.sanitise_action_callable.invoke({"monitored_variables": monitored_vars})
                elif callable(self.sanitise_action_callable):
                    res = self.sanitise_action_callable(monitored_vars)
                    if hasattr(res, "__await__"):
                        res = await res
                else:
                    raise ValueError(f"Unsupported callable: {type(self.sanitise_action_callable)}")

                # If list of content blocks (standard for langchain_mcp_adapters), extract text
                if isinstance(res, list) and len(res) > 0:
                    first_item = res[0]
                    if isinstance(first_item, dict) and "text" in first_item:
                        res = first_item["text"]
                    elif isinstance(first_item, str):
                        res = first_item

                # Parse JSON string if response is str
                if isinstance(res, str):
                    res_data = json.loads(res)
                elif isinstance(res, dict):
                    res_data = res
                else:
                    res_data = {"status": "error", "message": f"Unexpected response type: {type(res)}"}

                if res_data.get("status") == "error":
                    verdict = "ERROR"
                    feedback = res_data.get("message", "Error reported by AsmetaS server.")
                else:
                    # Enforce A2A Agent Card schema contract
                    try:
                        validated = SanitiseContractResult.model_validate(res_data)
                        verdict = validated.verdict
                        sanitised_val = validated.sanitised_action
                        feedback = validated.feedback
                        raw_output = validated.raw_output or {}

                        # Apply reverse action mapping if applicable
                        if sanitised_val and self.action_mapping:
                            reverse_map = {v: k for k, v in self.action_mapping.items()}
                            if sanitised_val in reverse_map:
                                sanitised_val = reverse_map[sanitised_val]
                    except ValidationError as val_err:
                        err_detail = val_err.errors()[0]["msg"] if val_err.errors() else str(val_err)
                        logger.error(f"A2A Contract Violation from AsmetaS enforcer: {val_err}")
                        verdict = "ERROR"
                        feedback = f"A2A Contract Violation: response schema mismatch ({err_detail})"
            else:
                # If no callable provided, default to bypass with warning
                verdict = "BYPASS"
                feedback = "Formal Gate running in mock/passthrough mode (no enforcer attached)."
                sanitised_val = monitored_vars.get("inputAction")

        except Exception as e:
            logger.error(f"Formal Gate evaluation error: {e}")
            verdict = "ERROR"
            feedback = f"Formal Gate exception: {str(e)}"

        # 4. Handle verdict and policies
        action_history = list(state.get("action_history", []))
        retry_count = state.get("retry_count", 0)

        # Handle ERROR with fallback policy
        if verdict == "ERROR":
            if self.error_policy == "fail_safe":
                verdict = "VIOLATION"
                sanitised_val = self.default_safe_action
                feedback = f"Formal gate offline/error ({feedback}). Fail-safe applied: defaulting to safe action '{self.default_safe_action}'."
            else:
                # fail_stop
                action_history.append({
                    "proposed_action": candidate_action,
                    "monitored_variables": monitored_vars,
                    "verdict": "ERROR",
                    "feedback": feedback,
                })
                # Add error tool message
                error_msg = ToolMessage(
                    content=f"[Formal Gate Critical Error] {feedback}",
                    tool_call_id=tool_call_id,
                    status="error",
                )
                return {
                    "guard_verdict": "ERROR",
                    "guard_feedback": feedback,
                    "candidate_action": candidate_action,
                    "sanitised_action": None,
                    "action_history": action_history,
                    "messages": [error_msg],
                }

        # Handle APPROVED
        if verdict == "APPROVED":
            sanitised_action = dict(candidate_action)
            action_history.append({
                "proposed_action": candidate_action,
                "monitored_variables": monitored_vars,
                "verdict": "APPROVED",
                "feedback": feedback,
                "raw_output": raw_output,
            })
            return {
                "guard_verdict": "APPROVED",
                "guard_feedback": feedback,
                "candidate_action": candidate_action,
                "sanitised_action": sanitised_action,
                "action_history": action_history,
            }

        # Handle VIOLATION
        if verdict == "VIOLATION":
            # Build sanitised action structure
            sanitised_args = dict(tool_args)
            if "inputAction" in sanitised_args:
                sanitised_args["inputAction"] = sanitised_val
            elif "action" in sanitised_args:
                sanitised_args["action"] = sanitised_val
            else:
                sanitised_args["inputAction"] = sanitised_val

            sanitised_action = {
                "name": tool_name,
                "args": sanitised_args,
                "id": tool_call_id,
            }

            action_history.append({
                "proposed_action": candidate_action,
                "monitored_variables": monitored_vars,
                "verdict": "VIOLATION",
                "sanitised_action": sanitised_action,
                "feedback": feedback,
                "raw_output": raw_output,
            })

            if self.policy == "replan":
                # Inject formal feedback into messages for the Planner to reflect and fix
                replan_feedback_msg = ToolMessage(
                    content=(
                        f"[Formal Gate Rejection] Action violates safety invariants. "
                        f"Feedback: {feedback}. Proposed action was rejected. "
                        f"Please propose an alternative safe action."
                    ),
                    tool_call_id=tool_call_id,
                    status="error",
                )
                return {
                    "guard_verdict": "VIOLATION",
                    "guard_feedback": feedback,
                    "candidate_action": candidate_action,
                    "sanitised_action": sanitised_action,
                    "action_history": action_history,
                    "retry_count": retry_count + 1,
                    "messages": [replan_feedback_msg],
                }
            else:
                # Shielding mode: overwrite candidate action with sanitised action
                # Update tool_calls in last AIMessage if present so environment executes sanitised action
                updated_messages = []
                if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    new_tool_calls = []
                    for tc in last_message.tool_calls:
                        if tc.get("id") == tool_call_id:
                            new_tc = dict(tc)
                            new_tc["args"] = sanitised_args
                            new_tool_calls.append(new_tc)
                        else:
                            new_tool_calls.append(tc)
                    # We can construct updated AIMessage or let environment read sanitised_action
                    last_message.tool_calls = new_tool_calls

                return {
                    "guard_verdict": "VIOLATION",
                    "guard_feedback": feedback,
                    "candidate_action": candidate_action,
                    "sanitised_action": sanitised_action,
                    "action_history": action_history,
                    "messages": updated_messages,
                }

        # Fallback / BYPASS
        return {
            "guard_verdict": "BYPASS",
            "guard_feedback": feedback or "Action bypassed formal gate.",
            "candidate_action": candidate_action,
            "sanitised_action": candidate_action,
            "action_history": action_history,
        }
