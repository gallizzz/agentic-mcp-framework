"""
Environment execution node for LangGraph.
Dispatches verified actions to connected environment tools (MCP actuators)
and tracks execution status in state.
"""
from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from agent.agent_state import AgentState


class EnvironmentNode:
    """Executes validated environment actions and logs execution records."""

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        self.tools = tools or []
        self._tool_node = ToolNode(self.tools) if self.tools else None

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        if not self._tool_node:
            return {}

        result = await self._tool_node.ainvoke(state)

        # Record action in state audit log
        executed_action = state.get("sanitised_action") or state.get("candidate_action")
        if executed_action:
            history = list(state.get("action_history") or [])
            history.append({
                "action": executed_action,
                "status": "EXECUTED",
                "verdict": state.get("guard_verdict"),
            })
            result["action_history"] = history

        # Enrich tool message if Formal Gate intervened (shielding applied)
        guard_verdict = state.get("guard_verdict")
        guard_feedback = state.get("guard_feedback")
        candidate_action = state.get("candidate_action")
        sanitised_action = state.get("sanitised_action")

        if guard_verdict == "VIOLATION" and result.get("messages"):
            for msg in result["messages"]:
                original_action_args = candidate_action.get("args") if candidate_action else {}
                shielded_action_args = sanitised_action.get("args") if sanitised_action else {}
                msg.content = (
                    f"[FORMAL GATE INTERVENTION - SHIELDING APPLIED]\n"
                    f"Azione originariamente proposta dal Planner: {original_action_args}\n"
                    f"Azione schermata/eseguita per sicurezza: {shielded_action_args}\n"
                    f"Motivazione del Formal Gate: {guard_feedback}\n"
                    f"Esito esecuzione nell'ambiente: {msg.content}\n\n"
                    f"ISTRUZIONE PER LA RISPOSTA: Spiega all'utente in modo trasparente che l'azione richiesta "
                    f"NON è stata eseguita come desiderato, ma è stata bloccata e sostituita con {shielded_action_args} "
                    f"dal Formal Gate per la seguente ragione: {guard_feedback}. "
                    f"Non affermare in nessun caso che l'azione originariamente richiesta ha avuto successo."
                )

        return result


def create_environment_node(tools: Optional[List[BaseTool]] = None) -> EnvironmentNode:
    return EnvironmentNode(tools=tools)
