"""LLM Planner Node for LangGraph.

LangGraph planner node for LLM reasoning and candidate action proposal.

The planner is the only component that talks to the LLM. It never executes tools: it only
emits tool calls, which the router sends to the Formal Gate. When the turn must end (step
limit reached, or the gate returned BLOCK) the LLM is called with tools disabled so it can
only write the final answer. The system prompt is generic (core/planner_prompt.md); domain text comes from `hints`.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from core.agent_state import AgentState

# Generic system prompt; the use case's hints are appended to it. The tools are not listed
# here: the LLM receives their schemas through `bind_tools`
SYSTEM_PROMPT_FILE = Path(__file__).resolve().parent / "planner_prompt.md"

# Sent only to the LLM, as last message, when the turn runs out of steps
STEP_LIMIT_REQUEST = (
    "[STEP LIMIT REACHED] You cannot perform any more actions in this turn; any earlier instruction "
    "to continue no longer applies. Answer the user now: report the real outcomes and list the requested "
    "actions that were NOT executed, saying that you can continue if they ask."
)
# The LLM may still return a tool call even with tools disabled: the user always gets an answer
FALLBACK_ANSWER = (
    "I had to interrupt the turn and could not prepare a summary: some requested actions "
    "may not have been executed. Ask me for the current state or to continue."
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
        # No tool call = the planner wrote its answer: the turn is over
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

# ============================================================================
# PLANNER NODE CLASS
# ============================================================================

class PlannerNode:
    """Generates next agent actions or responses using the LLM."""

    def __init__(self, llm: Any, tools: List[BaseTool], max_steps: int, hints: str):
        self.max_steps = max_steps
        # Generic prompt + the use case's hints (a missing file stops startup)
        base = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").rstrip()
        self.system_prompt = base + (f"\n\n### USE-CASE INSTRUCTIONS:\n{hints.strip()}" if hints.strip() else "")
        self.llm_with_tools = llm.bind_tools(tools)
        # Same tool schemas (the history contains tool calls), but calling them is forbidden
        self.llm_final = llm.bind_tools(tools, tool_choice="none")

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        """One LLM call. Normal case: tools enabled. Final-answer case (BLOCK or step limit):
        tools disabled, so the user always gets an explanation instead of a silent stop."""
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
