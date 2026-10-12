"""LLM Planner Node for LangGraph.

LangGraph planner node for LLM reasoning and candidate action proposal.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from agent.agent_state import AgentState

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_planner_node(llm: Any, tools: Optional[List[BaseTool]] = None, system_prompt: Optional[str] = None) -> PlannerNode:
    """Factory function to instantiate the PlannerNode."""
    return PlannerNode(llm=llm, tools=tools, system_prompt=system_prompt)

def planner_router(state: AgentState) -> str:
    """Route tool calls to formal_gate, or terminate turn if no tools were called."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Prevent runaway tool calling loops in the same turn
        action_history = state.get("action_history", [])
        if len(action_history) >= 3:
            return END
        return "formal_gate"
    return END

def build_default_system_prompt(tools: Optional[List[BaseTool]] = None) -> str:
    """Default system prompt for the planner LLM, injecting available tools."""
    tool_names = [t.name for t in tools] if tools else []
    return (
        f"Sei un assistente intelligente che opera all'interno di un sistema critico verificato formalmente.\n"
        f"Hai a disposizione i seguenti tool per interagire con l'ambiente: {tool_names}.\n"
        f"Quando l'utente richiede un'azione o invia comandi operativi, rispetta scrupolosamente le specifiche indicate nel prompt:\n"
        f"- Se l'utente specifica un incremento/decremento numerico di velocità (es. 'accelera di 10 km/h'), usa 'FASTER' o 'SLOWER' passando il relativo 'speed_delta' (es. speed_delta=10).\n"
        f"- Se l'utente fa riferimento allo stato dei sensori (es. corsia destra libera o occupata), imposta 'right_lane_free' (True o False).\n"
        f"- Per mantenere la velocità usa 'KEEP' o 'IDLE', per fermarsi 'STOP', per spostarsi 'LANE_RIGHT' o 'LANE_LEFT'.\n"
        f"Tutte le azioni sono sottoposte ad un Formal Gate deterministico basato su specifiche formali AsmetaS (es. regola 'Keep right if right lane free': se la corsia di destra è libera, l'azione viene forzata a LANE_RIGHT per sicurezza).\n"
        f"IMPORTANTE:\n"
        f"- Se il tool riporta un intervento di sicurezza [FORMAL GATE INTERVENTION - SHIELDING APPLIED], DEVI spiegare con precisione all'utente che l'azione originariamente richiesta NON è stata eseguita tal quale, bensì schermata/modificata dal Formal Gate con l'azione sicura indicata, specificando la motivazione fornita dal Formal Gate. È TASSATIVAMENTE VIETATO affermare che l'azione originariamente richiesta ha avuto successo.\n"
        f"- Se l'azione richiesta è già stata eseguita dall'ambiente, NON richiamare nuovamente il tool in loop. Rispondi direttamente all'utente spiegando sinteticamente l'esito reale dell'azione.\n"
        f"Sii sintetico, chiaro e professionale."
    )

# ============================================================================
# PLANNER NODE CLASS
# ============================================================================

class PlannerNode:
    """Generates next agent actions or responses using the LLM."""

    def __init__(self, llm: Any, tools: Optional[List[BaseTool]] = None, system_prompt: Optional[str] = None):
        self.llm = llm
        self.tools = tools or []
        self.system_prompt = (
            system_prompt
            or os.getenv("SYSTEM_PROMPT")
            or build_default_system_prompt(self.tools)
        )
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        # Ensure system prompt is prepended once
        if self.system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            messages = [SystemMessage(content=self.system_prompt)] + messages

        response = await self.llm_with_tools.ainvoke(messages)
        return {"messages": [response]}
