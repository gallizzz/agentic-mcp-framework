"""State definition for LangGraph.

Describes the structure of the agent's state.
"""

from typing import Annotated, List, Literal, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """LangGraph state tracking the conversation and the formal verdicts."""

    # Conversation state (add_messages appends instead of overwriting; kept across turns)
    messages: Annotated[List[AnyMessage], add_messages]

    # Formal gate evaluation of the last tool call (reset at every user message).
    # BYPASS = read-only tool run directly; APPROVED = executed as requested;
    # SHIELDED = executed after correction; REPLAN = nothing executed, try again;
    # BLOCKED = nothing executed, answer only; ERROR = operational failure, turn ends.
    guard_verdict: Optional[
        Literal["APPROVED", "ERROR", "BYPASS", "SHIELDED", "REPLAN", "BLOCKED"]
    ]
    guard_feedback: Optional[str]  # human-readable reason, shown in the console

    # Execution controls & limits
    planner_steps: int  # LLM calls in this turn, compared with max_steps_per_turn
    final_answer_only: bool  # set by the gate: the Planner may only reply, never act
