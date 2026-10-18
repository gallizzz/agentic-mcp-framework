"""LLM Planner Node for LangGraph.

LangGraph planner node for LLM reasoning and candidate action proposal.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from core.agent_state import AgentState

# Upper bound on gated actions per user turn (prevents runaway tool-calling loops)
MAX_ACTIONS_PER_TURN = 3

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

    if not getattr(messages[-1], "tool_calls", None):
        return END
    if len(state.get("action_history", [])) >= MAX_ACTIONS_PER_TURN:
        return END
    return "formal_gate"

def build_default_system_prompt(tools: Optional[List[BaseTool]] = None) -> str:
    """Builds a dynamic, generic system prompt for the planner LLM, injecting available tools."""
    if tools:
        tools_str = "\n".join(
            f"- `{t.name}`: {t.description.strip() if t.description else 'Nessuna descrizione fornita.'}"
            for t in tools
        )
    else:
        tools_str = "- Nessun tool connesso."

    return (
        "Sei un assistente operativo autonomo che controlla un sistema critico protetto da verifica formale deterministica.\n\n"
        "### STRUMENTI OPERATIVI DISPONIBILI:\n"
        f"{tools_str}\n\n"
        "### REGOLE OPERATIVE:\n"
        "1. **Interazione con l'Ambiente:** Quando l'utente richiede un'operazione o fornisce comandi, "
        "utilizza esclusivamente gli strumenti disponibili, rispettando scrupolosamente i tipi, le descrizioni e i vincoli "
        "dei parametri descritti nei rispettivi schemi.\n"
        "2. **Ciclo Percezione-Azione e Aggiornamento Contesto:**\n"
        "   - Se ti servono informazioni sullo stato dell'ambiente e hai a disposizione tool di lettura/ispezione, invocali per verificare lo stato.\n"
        "   - **Priorità delle condizioni indicate dall'utente:** Se l'utente specifica o dichiara esplicitamente nel messaggio lo stato di un sensore, una lettura o una condizione ambientale (es. per simulare o comunicare una variazione del contesto), imposta il relativo parametro con il valore indicato dall'utente, dando priorità a tale specifica rispetto a letture storiche o telemetrie precedenti.\n"
        "3. **Formal Gate & Shielding:** Tutte le azioni verso l'ambiente sono intercettate ed esaminate da un enforcer formale (Formal Gate).\n"
        "   - Se l'esecuzione riporta `[FORMAL GATE INTERVENTION - SHIELDING APPLIED]`, significa che l'azione "
        "originariamente proposta violava le proprietà formali di sicurezza ed è stata automaticamente schermata/sostituita con un'azione sicura.\n"
        "   - In questo caso, DEVI spiegare all'utente in modo trasparente che l'azione richiesta NON è stata eseguita "
        "nella forma originale ma è stata modificata dal Formal Gate, specificando chiaramente l'azione sicura eseguita e la motivazione.\n"
        "   - È TASSATIVAMENTE VIETATO affermare che l'azione originariamente richiesta ha avuto successo se è stata schermata.\n"
        "4. **Anti-Loop:** Se un'azione richiesta è già stata eseguita dall'ambiente, NON richiamare nuovamente il tool in loop. "
        "Rispondi direttamente all'utente spiegando sinteticamente l'esito reale dell'azione.\n"
        "Sii sintetico, chiaro e professionale."
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
