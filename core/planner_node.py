"""LLM Planner Node for LangGraph.

LangGraph planner node for LLM reasoning and candidate action proposal.

The planner is the only component that talks to the LLM. It never executes tools: it only
emits tool calls, which the router sends to the Formal Gate. When the turn must end (step
limit reached, or the gate returned BLOCK) the LLM is called with tools disabled so it can
only write the final answer. The system prompt is generic; domain text comes from `hints`.
"""

from __future__ import annotations
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from core.agent_state import AgentState

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

def build_default_system_prompt(tools: List[BaseTool], hints: str) -> str:
    """Builds a dynamic, generic system prompt for the planner LLM, injecting available tools."""
    tools_str = "\n".join(
        f"- `{t.name}`: {t.description.strip() if t.description else 'No description provided.'}"
        for t in tools
    )

    return (
        "You are an autonomous operations assistant that controls a critical system protected by deterministic formal verification.\n\n"
        "### AVAILABLE TOOLS:\n"
        f"{tools_str}\n\n"
        "### OPERATING RULES:\n"
        "1. **Interacting with the environment:** When the user requests an operation or gives commands, "
        "use only the available tools, strictly following the types, descriptions and constraints "
        "of the parameters in their schemas.\n"
        "2. **Perception-action loop:** If you need information about the state of the environment and a read/inspection tool is available, call it to check the state. "
        "Readings in earlier messages may be out of date: reread the state before acting.\n"
        "3. **Formal Gate & Shielding:** Every action towards the environment is intercepted and examined by a formal enforcer (the Formal Gate). "
        "The outcome of the verification is reported at the start of the tool result and is the only source to use when describing it.\n"
        "   - `[FORMAL GATE: ALLOW]`: the action was verified and executed exactly as proposed. "
        "Report the outcome without claiming that the Formal Gate intervened, even if the state looks unfavorable to you: "
        "the safety assessment belongs exclusively to the Formal Gate.\n"
        "   - `[FORMAL GATE: REPLACE - SHIELDING APPLIED]`: the action originally proposed violated the formal "
        "safety properties and was replaced with a safe action. In the final answer you MUST explain transparently to the user that the requested action "
        "was NOT executed in its original form, stating the safe action that was executed and the reason. "
        "You are STRICTLY FORBIDDEN to claim that the originally requested action succeeded.\n"
        "   - `[FORMAL GATE: REPLAN]`: the action was NOT executed and the state has not changed. Use the reason given "
        "to propose an alternative, rereading the state first if needed, or explain to the user why the request cannot be fulfilled.\n"
        "   - `[FORMAL GATE: BLOCK]`: the action was blocked and NOT executed. Explain the reason given to the user "
        "and what could change in the request; you cannot perform any other action in this turn.\n"
        "   - Do not infer Formal Gate interventions that the result does not report, and never write these markers in your own answers.\n"
        "4. **One tool call per response:** Each of your responses may contain at most one tool call; "
        "additional calls in the same response are not executed. You can still make several calls in sequence "
        "within the same turn: for example, first read the state of the environment and, once you have the result, propose the action. "
        "The limit applies to tool calls, not to actions: a single `submit_plan` call must contain ALL the actions "
        "the user requested, in order, even though only the first one is applied by that call. "
        "Never drop later actions and never ask the user again for data they already gave.\n"
        "5. **Reasons:** When a result carries a `reason`, explain it to the user using only its `reason_explanation`, "
        "in the user's language and without quoting it, and without adding causes the result does not state. Never invent limits, gaps or rules: only the enforcer decides them.\n"
        "6. **Anti-loop:** Do not repeat an action already executed in the same turn. "
        "Always report the real outcome of the actions executed in this turn, even if the environment was already in the requested state.\n"
        "Reply in the language the user writes in. Be concise, clear and professional."
        + (f"\n\n### USE-CASE INSTRUCTIONS:\n{hints.strip()}" if hints.strip() else "")
    )

# ============================================================================
# PLANNER NODE CLASS
# ============================================================================

class PlannerNode:
    """Generates next agent actions or responses using the LLM."""

    def __init__(self, llm: Any, tools: List[BaseTool], max_steps: int, hints: str):
        self.max_steps = max_steps
        # Generic prompt + the tool list discovered via MCP + the use case's hints
        self.system_prompt = build_default_system_prompt(tools, hints)
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
