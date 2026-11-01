"""State definition for LangGraph.

Describes the structure of the agent's state.
"""

from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """LangGraph state tracking reasoning, candidate actions, and formal verdicts."""

    # Conversation state
    messages: Annotated[List[AnyMessage], add_messages]

    # Candidate and sanitised action payloads
    candidate_action: Optional[Dict[str, Any]]
    sanitised_action: Optional[Dict[str, Any]]

    # Formal gate evaluation
    guard_verdict: Optional[
        Literal["APPROVED", "VIOLATION", "ERROR", "BYPASS", "SHIELDED", "REPLAN", "BLOCKED"]
    ]
    guard_feedback: Optional[str]

    # Execution controls & limits
    planner_steps: int
    final_answer_only: bool  # set by the gate: the Planner may only reply, never act
