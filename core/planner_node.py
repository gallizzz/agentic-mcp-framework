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

# Default upper bound on tool-calling rounds per user turn (prevents runaway loops and endless
# replanning); a use case can override it with `max_steps_per_turn`.
MAX_STEPS_PER_TURN = 3

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_planner_node(
    llm: Any,
    tools: Optional[List[BaseTool]] = None,
    system_prompt: Optional[str] = None,
    max_steps: int = MAX_STEPS_PER_TURN,
    hints: str = "",
) -> PlannerNode:
    """Factory function to instantiate the PlannerNode."""
    return PlannerNode(llm=llm, tools=tools, system_prompt=system_prompt, max_steps=max_steps, hints=hints)

def create_planner_router(max_steps: int = MAX_STEPS_PER_TURN):
    """Routes tool calls to formal_gate, or terminates the turn if no tools were called."""

    def planner_router(state: AgentState) -> str:
        messages = state.get("messages", [])
        if not messages:
            return END

        if not getattr(messages[-1], "tool_calls", None):
            return END
        # Fail-closed: after a blocking verdict no further action reaches the gate
        if state.get("final_answer_only") or state.get("planner_steps", 0) > max_steps:
            return END
        return "formal_gate"

    return planner_router

def build_default_system_prompt(tools: Optional[List[BaseTool]] = None, hints: str = "") -> str:
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
        "3. **Formal Gate & Shielding:** Tutte le azioni verso l'ambiente sono intercettate ed esaminate da un enforcer formale (Formal Gate). "
        "L'esito della verifica è riportato all'inizio del risultato del tool, ed è l'unica fonte da usare per descriverlo.\n"
        "   - `[FORMAL GATE: APPROVED]`: l'azione è stata verificata ed eseguita esattamente come proposta. "
        "Riporta l'esito senza affermare che il Formal Gate sia intervenuto, anche se i valori dei sensori ti sembrano sfavorevoli: "
        "la valutazione di sicurezza spetta esclusivamente al Formal Gate.\n"
        "   - `[FORMAL GATE INTERVENTION - SHIELDING APPLIED]`: l'azione originariamente proposta violava le proprietà formali "
        "di sicurezza ed è stata sostituita con un'azione sicura. DEVI spiegare all'utente in modo trasparente che l'azione richiesta "
        "NON è stata eseguita nella forma originale, specificando l'azione sicura eseguita e la motivazione. "
        "È TASSATIVAMENTE VIETATO affermare che l'azione originariamente richiesta ha avuto successo.\n"
        "   - `[FORMAL GATE: REPLAN]`: l'azione NON è stata eseguita e lo stato non è cambiato. Usa il motivo indicato "
        "per proporre un'alternativa, rileggendo prima lo stato se serve, oppure spiega all'utente perché la richiesta non è realizzabile.\n"
        "   - `[FORMAL GATE: BLOCKED]`: l'azione è stata bloccata e NON eseguita. Spiega all'utente il motivo indicato "
        "e cosa potrebbe cambiare nella richiesta; non puoi eseguire altre azioni in questo turno.\n"
        "   - Non dedurre interventi del Formal Gate che il risultato non riporta e non scrivere mai questi marker nelle tue risposte.\n"
        "4. **Una Chiamata a Tool per Risposta:** Ogni tua risposta può contenere al massimo una chiamata a tool; "
        "le chiamate aggiuntive nella stessa risposta non vengono eseguite. Puoi però eseguire più chiamate in sequenza "
        "nello stesso turno: ad esempio leggi prima lo stato dell'ambiente e, ricevuto il risultato, proponi l'azione.\n"
        "5. **Anti-Loop:** Non ripetere nello stesso turno un'azione già eseguita. "
        "Riporta sempre l'esito reale delle azioni eseguite in questo turno, anche se lo stato dell'ambiente era già quello richiesto.\n"
        "Sii sintetico, chiaro e professionale."
        + (f"\n\n### ISTRUZIONI DEL CASO DI STUDIO:\n{hints.strip()}" if hints.strip() else "")
    )

# ============================================================================
# PLANNER NODE CLASS
# ============================================================================

class PlannerNode:
    """Generates next agent actions or responses using the LLM."""

    def __init__(
        self,
        llm: Any,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        max_steps: int = MAX_STEPS_PER_TURN,
        hints: str = "",
    ):
        self.llm = llm
        self.tools = tools or []
        self.max_steps = max_steps
        self.system_prompt = (
            system_prompt
            or os.getenv("SYSTEM_PROMPT")
            or build_default_system_prompt(self.tools, hints)
        )
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm
        # Same tool schemas (the history contains tool calls), but calling them is forbidden
        self.llm_final = (
            self.llm.bind_tools(self.tools, tool_choice="none") if self.tools else self.llm
        )

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        # Ensure system prompt is prepended once
        if self.system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            messages = [SystemMessage(content=self.system_prompt)] + messages

        steps = state.get("planner_steps", 0)
        final_only = state.get("final_answer_only") or steps >= self.max_steps
        llm = self.llm_final if final_only else self.llm_with_tools
        response = await llm.ainvoke(messages)
        return {"messages": [response], "planner_steps": steps + 1}
