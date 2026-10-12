"""State definition for LangGraph.

Describes the structure of the agent's state.
"""

from typing import Annotated, Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    LangGraph state tracking the lifecycle of agent reasoning,
    formal action interception, sanitisation, and environment execution.
    """
    # Standard conversation messages (HumanMessage, AIMessage, ToolMessage)
    messages: Annotated[List[AnyMessage], add_messages]

    # Candidate action proposed by Planner
    # e.g. {"name": "execute_vehicle_action", "args": {"inputAction": "FASTER", "rightLaneFree": "false"}}
    candidate_action: Optional[Dict[str, Any]]

    # Variables monitored by AsmetaS formal guard
    # e.g. {"inputAction": "FASTER", "rightLaneFree": "false"}
    monitored_variables: Dict[str, str]

    # Formal Gate evaluation verdict
    guard_verdict: Optional[Literal["APPROVED", "VIOLATION", "ERROR", "BYPASS"]]

    # Action sanitised by AsmetaS (if violated or modified)
    sanitised_action: Optional[Dict[str, Any]]

    # Formal explanation/feedback provided by AsmetaS
    guard_feedback: Optional[str]

    # Number of re-planning attempts for the current turn
    retry_count: int

    # Maximum allowed re-planning retries before fail-stop
    max_retries: int

    # Enforcer session ID from AsmetaS runtime
    execution_id: Optional[str]

    # Audit history of actions and formal gate interventions
    action_history: List[Dict[str, Any]]

# Backward compatibility alias
FormalAgentState = AgentState

