"""LLM Planner Node for LangGraph.

LangGraph planner node for LLM reasoning and candidate action proposal.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from core.agent_state import AgentState

# Sent only to the LLM, as last message, when the turn runs out of steps
STEP_LIMIT_REQUEST = (
    "[LIMITE DI PASSI RAGGIUNTO] Non puoi eseguire altre azioni in questo turno, qualsiasi istruzione "
    "precedente non vale più. Rispondi ora all'utente: riporta gli esiti reali ed elenca le azioni "
    "richieste che NON sono state eseguite, dicendo che puoi proseguire se te lo chiede."
)
# The LLM may still return a tool call even with tools disabled: the user always gets an answer
FALLBACK_ANSWER = (
    "Ho dovuto interrompere il turno e non sono riuscito a preparare un riepilogo: alcune azioni "
    "richieste potrebbero non essere state eseguite. Chiedimi lo stato attuale o di proseguire."
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_planner_node(llm: Any, tools: List[BaseTool], max_steps: int, hints: str) -> PlannerNode:
    """Factory function to instantiate the PlannerNode."""
    return PlannerNode(llm=llm, tools=tools, max_steps=max_steps, hints=hints)

def create_planner_router(max_steps: int):
    """Routes tool calls to formal_gate, or terminates the turn if no tools were called."""

    def planner_router(state: AgentState) -> str:
        if not getattr(state["messages"][-1], "tool_calls", None):
            return END
        # Fail-closed: after a blocking verdict no further action reaches the gate
        if state.get("final_answer_only") or state.get("planner_steps", 0) > max_steps:
            return END
        return "formal_gate"

    return planner_router

def _answer_pending_tool_calls(messages: List[AnyMessage]) -> List[AnyMessage]:
    """Answers tool calls left without a result by a turn that ended early, as the LLM requires."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    result = []
    for message in messages:
        result.append(message)
        for tc in getattr(message, "tool_calls", None) or []:
            if tc.get("id") not in answered:
                result.append(ToolMessage(
                    content="[Formal Gate] Not executed: the turn ended before this action was evaluated.",
                    tool_call_id=tc.get("id"),
                    status="error",
                ))
    return result

def build_default_system_prompt(tools: List[BaseTool], hints: str) -> str:
    """Builds a dynamic, generic system prompt for the planner LLM, injecting available tools."""
    tools_str = "\n".join(
        f"- `{t.name}`: {t.description.strip() if t.description else 'Nessuna descrizione fornita.'}"
        for t in tools
    )

    return (
        "Sei un assistente operativo autonomo che controlla un sistema critico protetto da verifica formale deterministica.\n\n"
        "### STRUMENTI OPERATIVI DISPONIBILI:\n"
        f"{tools_str}\n\n"
        "### REGOLE OPERATIVE:\n"
        "1. **Interazione con l'Ambiente:** Quando l'utente richiede un'operazione o fornisce comandi, "
        "utilizza esclusivamente gli strumenti disponibili, rispettando scrupolosamente i tipi, le descrizioni e i vincoli "
        "dei parametri descritti nei rispettivi schemi.\n"
        "2. **Ciclo Percezione-Azione:** Se ti servono informazioni sullo stato dell'ambiente e hai a disposizione tool di lettura/ispezione, invocali per verificare lo stato. "
        "Le letture dei messaggi precedenti possono essere superate: prima di agire rileggi lo stato.\n"
        "3. **Formal Gate & Shielding:** Tutte le azioni verso l'ambiente sono intercettate ed esaminate da un enforcer formale (Formal Gate). "
        "L'esito della verifica è riportato all'inizio del risultato del tool, ed è l'unica fonte da usare per descriverlo.\n"
        "   - `[FORMAL GATE: APPROVED]`: l'azione è stata verificata ed eseguita esattamente come proposta. "
        "Riporta l'esito senza affermare che il Formal Gate sia intervenuto, anche se lo stato ti sembra sfavorevole: "
        "la valutazione di sicurezza spetta esclusivamente al Formal Gate.\n"
        "   - `[FORMAL GATE INTERVENTION - SHIELDING APPLIED]`: l'azione originariamente proposta violava le proprietà formali "
        "di sicurezza ed è stata sostituita con un'azione sicura. Nella risposta finale DEVI spiegare all'utente in modo trasparente che l'azione richiesta "
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

    def __init__(self, llm: Any, tools: List[BaseTool], max_steps: int, hints: str):
        self.max_steps = max_steps
        self.system_prompt = os.getenv("SYSTEM_PROMPT") or build_default_system_prompt(tools, hints)
        self.llm_with_tools = llm.bind_tools(tools)
        # Same tool schemas (the history contains tool calls), but calling them is forbidden
        self.llm_final = llm.bind_tools(tools, tool_choice="none")

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        steps = state["planner_steps"]
        out_of_steps = steps >= self.max_steps
        messages = [SystemMessage(content=self.system_prompt)] + _answer_pending_tool_calls(state["messages"])

        if state["final_answer_only"] or out_of_steps:
            request = [HumanMessage(content=STEP_LIMIT_REQUEST)] if out_of_steps else []
            response = await self.llm_final.ainvoke(messages + request)
            if response.tool_calls or not response.content:
                response = AIMessage(content=FALLBACK_ANSWER)
        else:
            response = await self.llm_with_tools.ainvoke(messages)
        return {"messages": [response], "planner_steps": steps + 1}
