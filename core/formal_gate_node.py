"""Formal Gate Node for LangGraph.

LangGraph node that sends every non-read-only action to the enforcement MCP server.
"""

import copy
import json
from typing import Any, Awaitable, Callable, Dict, Optional, Set, Tuple
import uuid
from langchain_core.messages import ToolMessage
from core.agent_state import AgentState
from core.mcp_utils import parse_mcp_response
from enforcement.contracts import SUBMIT_ARGUMENT, SUBMIT_TOOL

# Async callable (tool args) -> (is_error, raw text result) bound to the MCP session
SubmitCallable = Callable[[Dict[str, Any]], Awaitable[Tuple[bool, str]]]

# Enforcement decision -> gate verdict
DECISION_VERDICTS = {
    "ALLOW": "APPROVED",
    "REPLACE": "SHIELDED",
    "REPLAN": "REPLAN",
    "BLOCK": "BLOCKED",
}

APPROVED_NOTICE = "[FORMAL GATE: APPROVED] Azione verificata ed eseguita esattamente come proposta."
REPLAN_NOTICE = "[FORMAL GATE: REPLAN] Nessuna modifica è stata applicata."
BLOCKED_NOTICE = "[FORMAL GATE: BLOCKED] Azione bloccata dall'enforcer formale."

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _extract_candidate_action(last_msg: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Returns the first tool call of the Planner message (the router only sends tool calls here)."""
    tc = last_msg.tool_calls[0]
    tool_call_id = tc.get("id")
    return {"name": tc["name"], "args": dict(tc.get("args") or {}), "id": tool_call_id}, tool_call_id

def _gate_result(
    verdict: str,
    feedback: Optional[str],
    candidate_action: Optional[Dict[str, Any]],
    executed_action: Optional[Dict[str, Any]],
    **extra: Any,
) -> Dict[str, Any]:
    """Builds the state update emitted by the Formal Gate."""
    return {
        "guard_verdict": verdict,
        "guard_feedback": feedback,
        "candidate_action": candidate_action,
        "executed_action": executed_action,
        **extra,
    }

def _compact_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Result shown to the Planner: drops per-step preview evidence, keeps its outcome."""
    compact = dict(result)
    preview = compact.get("preview")
    if isinstance(preview, dict):
        compact["preview"] = {"outcome": preview.get("outcome")}
    return compact

def _shielding_notice(
    submitted: Dict[str, Any],
    executed: Dict[str, Any],
    feedback: str,
    execution_result: str,
) -> str:
    """Tells the Planner that the enforcer replaced the proposed action."""
    original_args = submitted.get("args")
    shielded_args = executed.get("args")
    return (
        f"[FORMAL GATE INTERVENTION - SHIELDING APPLIED]\n"
        f"Azione originariamente proposta dal Planner: {original_args}\n"
        f"Azione schermata/eseguita per sicurezza: {shielded_args}\n"
        f"Motivazione del Formal Gate: {feedback}\n"
        f"Esito esecuzione nell'ambiente: {execution_result}\n\n"
        f"ISTRUZIONE PER LA RISPOSTA FINALE: Spiega all'utente in modo trasparente che l'azione richiesta "
        f"NON è stata eseguita come desiderato, ma è stata bloccata e sostituita con {shielded_args} "
        f"dal Formal Gate per la seguente ragione: {feedback}. "
        f"Non affermare in nessun caso che l'azione originariamente richiesta ha avuto successo."
    )

def _remaining_actions_notice(submitted: Dict[str, Any]) -> str:
    """Tells the Planner to continue the plan: only its first action has been executed."""
    submission = submitted["args"].get(SUBMIT_ARGUMENT)
    actions = submission.get("actions") if isinstance(submission, dict) else None
    remaining = actions[1:] if isinstance(actions, list) else []
    if not remaining:
        return ""
    return (
        f"\n\nAZIONI DEL PIANO ANCORA DA ESEGUIRE: {remaining}\n"
        "ISTRUZIONE: non rispondere ancora all'utente. Rileggi lo stato e invia un nuovo piano con "
        "queste azioni. Spiega gli esiti all'utente solo quando il piano è completato o non può proseguire."
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

    Fail-closed: read-only tools go to the Environment, the submit tool goes to the
    enforcement server (which verifies AND executes), every other tool is blocked.
    """

    def __init__(self, submit_callable: SubmitCallable, read_only_tools: Set[str]):
        self.submit_callable = submit_callable
        self.read_only_tools = set(read_only_tools)

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
        last_msg = state["messages"][-1]
        result = await self._evaluate(last_msg)
        skipped_messages = _skip_extra_tool_calls(last_msg)
        if skipped_messages:
            result["messages"] = list(result.get("messages") or []) + skipped_messages
        return result

    async def _evaluate(self, last_msg: Any) -> Dict[str, Any]:
        candidate_action, tool_call_id = _extract_candidate_action(last_msg)
        tool_name = candidate_action["name"]

        # Only tools explicitly declared read-only skip formal verification
        if tool_name in self.read_only_tools:
            return _gate_result(
                "BYPASS", f"Tool '{tool_name}' is declared read-only.",
                candidate_action, candidate_action,
            )

        if tool_name != SUBMIT_TOOL:
            return self._block(
                f"Tool '{tool_name}' is neither read-only nor the submit tool '{SUBMIT_TOOL}'.",
                candidate_action, tool_call_id,
            )

        args = copy.deepcopy(candidate_action["args"])
        if isinstance(args.get(SUBMIT_ARGUMENT), dict):
            # A fresh ID per submission: the LLM never chooses or reuses it
            args[SUBMIT_ARGUMENT]["request_id"] = f"req-{uuid.uuid4().hex[:12]}"
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
        verdict = DECISION_VERDICTS.get(decision)
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
            content += _remaining_actions_notice(submitted)
        elif verdict == "APPROVED":
            content = f"{APPROVED_NOTICE}\n{result_text}{_remaining_actions_notice(submitted)}"
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
