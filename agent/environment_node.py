"""
Environment Node for LangGraph.
Executes approved/sanitised actions on environment tools (Vehicle Actuator MCP server)
and tracks execution status within the agent state.
"""
from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from agent.agent_state import AgentState


class EnvironmentNode:
    """
    Environment Node responsible for executing authorised candidate or sanitised actions
    on the physical or simulated environment tools.
    """

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        self.tools = tools or []
        self._tool_node = ToolNode(self.tools) if self.tools else None

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Executes authorised tool calls in the environment and logs action history.
        """
        if not self._tool_node:
            return {}

        result = await self._tool_node.ainvoke(state)

        # Update action audit history if an action was executed
        executed_action = state.get("sanitised_action") or state.get("candidate_action")
        if executed_action:
            history = list(state.get("action_history") or [])
            history.append({
                "action": executed_action,
                "status": "EXECUTED",
                "verdict": state.get("guard_verdict"),
            })
            result["action_history"] = history

        return result


def create_environment_node(tools: Optional[List[BaseTool]] = None) -> EnvironmentNode:
    """
    Factory function returning an instantiated EnvironmentNode.
    """
    return EnvironmentNode(tools=tools)
