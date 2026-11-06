"""Formal Gate Node for LangGraph.

LangGraph node between the Planner and the enforcement MCP server: it runs the read-only
tools directly and sends every action to the server, which verifies and executes it.

Decision table for the FIRST tool call of the planner message (fail-closed):

    read-only tool (readOnlyHint)  -> run directly                       verdict BYPASS
    any other tool but submit_plan -> not run, turn ends                 verdict ERROR
    submit_plan                    -> sent to the server; its answer is
        rejected before the ASMs (schema/binding)                        verdict REPLAN
        decision ALLOW / REPLACE / REPLAN / BLOCK                        APPROVED / SHIELDED / REPLAN / BLOCKED
        operational failure or unknown decision                          verdict ERROR (turn ends)

The gate never decides: the decision comes from the ASM models behind the server and is only
translated (`DECISION_VERDICTS`) into a message the planner LLM can use.
"""

import copy
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import uuid
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from core.agent_state import AgentState
from enforcement.contracts import DECISION_VERDICTS, SUBMIT_ARGUMENT, SUBMIT_TOOL

# Async callable (tool args) -> (is_error, raw text result) bound to the MCP session
SubmitCallable = Callable[[Dict[str, Any]], Awaitable[Tuple[bool, str]]]

APPROVED_NOTICE = "[FORMAL GATE: APPROVED] Action verified and executed exactly as proposed."
REPLAN_NOTICE = "[FORMAL GATE: REPLAN] No change was applied."
BLOCKED_NOTICE = "[FORMAL GATE: BLOCKED] Action blocked by the formal enforcer."

# What an operational failure did to the live system (the turn ends right after it)
COMMIT_OUTCOME_NOTICES = {
    "applied": "the command WAS APPLIED to the system",
    "not_applied": "the command was NOT applied",
    "unknown": "it is UNKNOWN whether the command was applied",
}
RECOVERY_NOTICE = "Changes are disabled until the agent is restarted."

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_mcp_response(raw: str) -> Dict[str, Any]:
    """Parses the text of an MCP tool result; anything but a JSON object gives an empty dict.

    Also used by agent_graph.py for the startup availability check."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

def _extract_candidate_action(last_msg: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Returns the first tool call of the Planner message (the router only sends tool calls here)."""
    tc = last_msg.tool_calls[0]
    tool_call_id = tc.get("id")
    return {"name": tc["name"], "args": dict(tc.get("args") or {}), "id": tool_call_id}, tool_call_id

def _gate_result(
    verdict: str,
    feedback: Optional[str],
    **extra: Any,
) -> Dict[str, Any]:
    """Builds the state update emitted by the Formal Gate."""
    return {
        "guard_verdict": verdict,
        "guard_feedback": feedback,
        **extra,
    }

def _compact_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Result shown to the Planner: drops per-step preview evidence, keeps its outcome."""
    compact = dict(result)
    preview = compact.get("preview")
    if isinstance(preview, dict):
        compact["preview"] = {"outcome": preview.get("outcome")}
    return compact

def _failure_feedback(result: Dict[str, Any], raw: str) -> str:
    """Describes an operational failure, including what it did to the live system."""
    status = result.get("status", "no status")
    parts = [f"Enforcement server error ({status}): {result.get('reason', raw)}."]
    outcome = COMMIT_OUTCOME_NOTICES.get(result.get("commit_outcome"))
    if outcome:
        parts.append(f"Outcome: {outcome}.")
    if result.get("applied_action"):
        parts.append(f"Applied action: {result['applied_action']}.")
    if status == "recovery_required":
        parts.append(RECOVERY_NOTICE)
    return " ".join(parts)

def _shielding_notice(
    submitted: Dict[str, Any],
    applied_action: Any,
    feedback: str,
    execution_result: str,
) -> str:
    """Tells the Planner that the enforcer replaced the proposed action."""
    return (
        f"[FORMAL GATE INTERVENTION - SHIELDING APPLIED]\n"
        f"Action originally proposed by the Planner: {submitted.get('args')}\n"
        f"Shielded action executed for safety: {applied_action}\n"
        f"Formal Gate reason: {feedback}\n"
        f"Execution outcome in the environment: {execution_result}\n\n"
        f"INSTRUCTION FOR THE FINAL ANSWER: Explain transparently to the user that the requested action "
        f"was NOT executed as desired, but was replaced by the Formal Gate with the shielded action "
        f"shown above, for the following reason: {feedback}. "
        f"Describe the action in the user's terms, without repeating this raw data. "
        f"Never claim that the originally requested action succeeded."
    )

def _remaining_actions_notice(submitted: Dict[str, Any]) -> str:
    """Tells the Planner to continue the plan: only its first action has been executed."""
    submission = submitted["args"].get(SUBMIT_ARGUMENT)
    actions = submission.get("actions") if isinstance(submission, dict) else None
    remaining = actions[1:] if isinstance(actions, list) else []
    if not remaining:
        return ""
    return (
        f"\n\nPLAN ACTIONS STILL TO EXECUTE IN THIS TURN: {remaining}\n"
        "INSTRUCTION: do not answer the user yet. Reread the state and submit a new plan with "
        "these actions. Explain the outcomes to the user only when the plan is complete or cannot continue. "
        "In later turns this list no longer applies: do not resume these actions unless the user asks."
    )

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
    """Deterministic gate for runtime action verification.

    Fail-closed: only read-only tools are run here, the submit tool goes to the
    enforcement server (which verifies AND executes), every other tool is blocked.
    """

    def __init__(self, submit_callable: SubmitCallable, read_only_tools: List[BaseTool]):
        # read_only_tools: only the tools the server annotated `readOnlyHint`
        self.submit_callable = submit_callable
        self.read_only_tools = {tool.name: tool for tool in read_only_tools}

    @staticmethod
    def _block(feedback: str, tool_call_id: Optional[str]) -> Dict[str, Any]:
        """Ends the turn with an error: no fallback action is attempted."""
        return _gate_result(
            "ERROR", feedback,
            messages=[
                ToolMessage(
                    content=f"[Formal Gate Error] {feedback}",
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        )

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        """LangGraph entry: evaluates the planner's last message (it always has tool calls)."""
        last_msg = state["messages"][-1]
        result = await self._evaluate(last_msg)
        skipped_messages = _skip_extra_tool_calls(last_msg)
        if skipped_messages:
            result["messages"] = list(result.get("messages") or []) + skipped_messages
        return result

    async def _evaluate(self, last_msg: Any) -> Dict[str, Any]:
        """Applies the decision table above to the first tool call of the message."""
        candidate_action, tool_call_id = _extract_candidate_action(last_msg)
        tool_name = candidate_action["name"]

        # Only tools explicitly declared read-only skip formal verification
        if tool_name in self.read_only_tools:
            return await self._read(candidate_action)

        if tool_name != SUBMIT_TOOL:
            return self._block(
                f"Tool '{tool_name}' is neither read-only nor the submit tool '{SUBMIT_TOOL}'.",
                tool_call_id,
            )

        args = copy.deepcopy(candidate_action["args"])
        if isinstance(args.get(SUBMIT_ARGUMENT), dict):
            # A fresh ID per submission: the LLM never chooses or reuses it
            args[SUBMIT_ARGUMENT]["request_id"] = f"req-{uuid.uuid4().hex[:12]}"
        submitted = {"name": tool_name, "args": args, "id": tool_call_id}

        try:
            is_error, raw = await self.submit_callable(args)
        except Exception as e:
            return self._block(f"Enforcement server unreachable: {e}", tool_call_id)

        # Interpret the server answer. `status` is "completed" when the ASMs decided,
        # "invalid_request" when the plan was refused before them, anything else is a failure.
        result = parse_mcp_response(raw)
        if is_error or result.get("status") == "invalid_request":
            # Rejected before reaching the ASM models (schema or binding validation)
            reason = result.get("reason") or raw
            return self._submit_result(
                "REPLAN", f"Request rejected before the ASM models: {reason}",
                submitted, result, tool_call_id,
            )
        if result.get("status") != "completed":
            return self._block(_failure_feedback(result, raw), tool_call_id)

        decision = result.get("decision")
        verdict = DECISION_VERDICTS.get(decision)
        if verdict is None:
            return self._block(f"Unmapped enforcement decision '{decision}'.", tool_call_id)
        return self._submit_result(
            verdict, f"{decision}: {result.get('reason')}",
            submitted, result, tool_call_id,
        )

    async def _read(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Runs a read-only tool: a failed read is reported to the Planner, it changes nothing."""
        tool_call = {**action, "type": "tool_call"}
        try:
            message = await self.read_only_tools[action["name"]].ainvoke(tool_call)
        except Exception as e:
            message = ToolMessage(
                content=f"[Formal Gate] Read failed: {e}", tool_call_id=action["id"], status="error",
            )
        return _gate_result(
            "BYPASS", f"Tool '{action['name']}' is declared read-only.", messages=[message],
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
        shown_feedback = feedback
        if verdict == "SHIELDED":
            applied_action = result.get("applied_action")
            shown_feedback = f"{feedback} | Applied: {applied_action}"
            content = _shielding_notice(submitted, applied_action, feedback, result_text)
            content += _remaining_actions_notice(submitted)
        elif verdict == "APPROVED":
            content = f"{APPROVED_NOTICE}\n{result_text}{_remaining_actions_notice(submitted)}"
        elif verdict == "REPLAN":
            content = f"{REPLAN_NOTICE} Reason: {feedback}\n{result_text}"
        else:
            content = f"{BLOCKED_NOTICE} Reason: {feedback}\n{result_text}"

        return _gate_result(
            verdict, shown_feedback,
            final_answer_only=verdict == "BLOCKED",
            messages=[
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                    status="success" if verdict in ("APPROVED", "SHIELDED") else "error",
                )
            ],
        )
