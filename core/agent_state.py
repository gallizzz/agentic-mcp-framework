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
    monitored_variables: Dict[str, str]
    guard_verdict: Optional[Literal["APPROVED", "VIOLATION", "ERROR", "BYPASS"]]
    guard_feedback: Optional[str]

    # Execution controls & limits
    planner_steps: int
    execution_id: Optional[str]

    # Audit history
    action_history: List[Dict[str, Any]]
