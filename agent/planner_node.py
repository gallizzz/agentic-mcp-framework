"""
Planner Node for LangGraph.
Coordinates user requests, reasoning, and candidate tool call generation.
"""
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END

from agent.agent_state import AgentState


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
        self.system_prompt = system_prompt
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
        return "formal_gate"
    return END
