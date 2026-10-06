import os
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END

from agent.agent_state import AgentState


def build_default_system_prompt(tools: Optional[List[BaseTool]] = None) -> str:
    """
    Constructs the default system prompt for the Planner LLM,
    injecting available tool names and operative guidance.
    """
    tool_names = [t.name for t in tools] if tools else []
    return (
        f"Sei un assistente intelligente che opera all'interno di un sistema critico verificato formalmente.\n"
        f"Hai a disposizione i seguenti tool per interagire con l'ambiente: {tool_names}.\n"
        f"Quando l'utente richiede un'azione o invia comandi operativi, rispetta scrupolosamente le specifiche indicate nel prompt:\n"
        f"- Se l'utente specifica un incremento/decremento numerico di velocità (es. 'accelera di 10 km/h'), usa 'FASTER' o 'SLOWER' passando il relativo 'speed_delta' (es. speed_delta=10).\n"
        f"- Se l'utente fa riferimento allo stato dei sensori (es. corsia destra libera o occupata), imposta 'right_lane_free' (True o False).\n"
        f"- Per mantenere la velocità usa 'KEEP' o 'IDLE', per fermarsi 'STOP', per spostarsi 'LANE_RIGHT' o 'LANE_LEFT'.\n"
        f"Tutte le azioni sono sottoposte ad un Formal Gate deterministico basato su specifiche formali AsmetaS (es. regola 'Keep right if right lane free': se la corsia di destra è libera, l'azione viene forzata a LANE_RIGHT per sicurezza).\n"
        f"IMPORTANTE: Se l'azione richiesta è già stata eseguita dall'ambiente o modificata dal Formal Gate (vedi output del tool), "
        f"NON richiamare nuovamente il tool in loop. Rispondi direttamente all'utente spiegando sinteticamente l'esito dell'azione "
        f"e le eventuali modifiche applicate dal Formal Gate per la sicurezza.\n"
        f"Sii sintetico, chiaro e professionale."
    )


class PlannerNode:
    """
    Planner LLM node that processes conversation history and proposes
    candidate actions bound to environment tools.
    """

    def __init__(
        self,
        llm: Any,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm = llm
        self.tools = tools or []
        self.system_prompt = (
            system_prompt
            or os.getenv("SYSTEM_PROMPT")
            or build_default_system_prompt(self.tools)
        )
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Executes the Planner LLM invocation.
        """
        messages = list(state.get("messages", []))
        # Prepend system prompt if provided and not already present
        if self.system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            messages = [SystemMessage(content=self.system_prompt)] + messages

        response = await self.llm_with_tools.ainvoke(messages)
        return {"messages": [response]}


def create_planner_node(
    llm: Any,
    tools: Optional[List[BaseTool]] = None,
    system_prompt: Optional[str] = None,
) -> PlannerNode:
    """
    Factory function returning an instantiated PlannerNode.
    """
    return PlannerNode(llm=llm, tools=tools, system_prompt=system_prompt)


def planner_router(state: AgentState) -> str:
    """
    Inspects planner output. If a tool call was proposed, route to Formal Gate.
    Otherwise, conversation is complete -> route to END.
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Safeguard: prevent runaway tool loops if multiple actions were already executed in turn
        action_history = state.get("action_history", [])
        if len(action_history) >= 3:
            return END
        return "formal_gate"
    return END
