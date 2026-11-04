"""Environment execution node for LangGraph.

LangGraph node that runs the read-only tools let through by the Formal Gate.
"""

from typing import Any, Dict, List
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from core.agent_state import AgentState

class EnvironmentNode:
    """Executes read-only tools; actions are executed by the enforcement server instead."""

    def __init__(self, read_only_tools: List[BaseTool]):
        self._tool_node = ToolNode(read_only_tools)

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        action = state["candidate_action"]
        # Execute only the call the Formal Gate evaluated, never others of the same message
        return await self._tool_node.ainvoke([{
            "name": action["name"],
            "args": action.get("args") or {},
            "id": action.get("id"),
            "type": "tool_call",
        }])

def create_environment_node(read_only_tools: List[BaseTool]) -> EnvironmentNode:
    return EnvironmentNode(read_only_tools)
