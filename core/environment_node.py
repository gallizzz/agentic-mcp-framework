"""Environment execution node for LangGraph.

LangGraph environment node for dispatching verified actions to MCP tools
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from core.agent_state import AgentState
from core.mcp_utils import mcp_result_text

APPROVED_NOTICE = "[FORMAL GATE: APPROVED] Azione verificata ed eseguita esattamente come proposta."

def _shielding_notice(
    candidate_action: Optional[Dict[str, Any]],
    sanitised_action: Optional[Dict[str, Any]],
    guard_feedback: Optional[str],
    execution_result: Any,
) -> str:
    """Wraps the environment output with the Formal Gate shielding explanation for the Planner."""
    original_action_args = candidate_action.get("args") if candidate_action else {}
    shielded_action_args = sanitised_action.get("args") if sanitised_action else {}
    return (
        f"[FORMAL GATE INTERVENTION - SHIELDING APPLIED]\n"
        f"Azione originariamente proposta dal Planner: {original_action_args}\n"
        f"Azione schermata/eseguita per sicurezza: {shielded_action_args}\n"
        f"Motivazione del Formal Gate: {guard_feedback}\n"
        f"Esito esecuzione nell'ambiente: {execution_result}\n\n"
        f"ISTRUZIONE PER LA RISPOSTA: Spiega all'utente in modo trasparente che l'azione richiesta "
        f"NON è stata eseguita come desiderato, ma è stata bloccata e sostituita con {shielded_action_args} "
        f"dal Formal Gate per la seguente ragione: {guard_feedback}. "
        f"Non affermare in nessun caso che l'azione originariamente richiesta ha avuto successo."
    )

class EnvironmentNode:
    """Executes validated environment actions and logs execution records."""

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        self.tools = tools or []
        self._tool_node = ToolNode(self.tools) if self.tools else None

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        guard_verdict = state.get("guard_verdict")
        candidate_action = state.get("candidate_action")
        sanitised_action = state.get("sanitised_action")
        executed_action = sanitised_action or candidate_action
        if not self._tool_node or not executed_action:
            return {}

        # Execute only the action the Formal Gate evaluated, never other calls of the same message
        result = await self._tool_node.ainvoke([{
            "name": executed_action["name"],
            "args": executed_action.get("args") or {},
            "id": executed_action.get("id"),
            "type": "tool_call",
        }])

        # Record action in state audit log
        result["action_history"] = list(state.get("action_history") or []) + [{
            "action": executed_action,
            "status": "EXECUTED",
            "verdict": guard_verdict,
        }]

        # State the gate verdict explicitly so the Planner never has to infer it
        for msg in result.get("messages") or []:
            if guard_verdict == "VIOLATION":
                msg.content = _shielding_notice(
                    candidate_action, sanitised_action, state.get("guard_feedback"),
                    mcp_result_text(msg.content),
                )
            elif guard_verdict == "APPROVED":
                msg.content = f"{APPROVED_NOTICE}\n{mcp_result_text(msg.content)}"

        return result

def create_environment_node(tools: Optional[List[BaseTool]] = None) -> EnvironmentNode:
    return EnvironmentNode(tools=tools)
