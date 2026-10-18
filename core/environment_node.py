"""Environment execution node for LangGraph.

LangGraph environment node for dispatching verified actions to MCP tools
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from core.agent_state import AgentState

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
        if not self._tool_node:
            return {}

        result = await self._tool_node.ainvoke(state)
        guard_verdict = state.get("guard_verdict")
        candidate_action = state.get("candidate_action")
        sanitised_action = state.get("sanitised_action")

        # Record action in state audit log
        executed_action = sanitised_action or candidate_action
        if executed_action:
            result["action_history"] = list(state.get("action_history") or []) + [{
                "action": executed_action,
                "status": "EXECUTED",
                "verdict": guard_verdict,
            }]

        # Enrich tool message if Formal Gate intervened (shielding applied)
        if guard_verdict == "VIOLATION":
            for msg in result.get("messages") or []:
                msg.content = _shielding_notice(
                    candidate_action, sanitised_action, state.get("guard_feedback"), msg.content
                )

        return result

def create_environment_node(tools: Optional[List[BaseTool]] = None) -> EnvironmentNode:
    return EnvironmentNode(tools=tools)
