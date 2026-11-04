"""The graph-based orchestrator for LangGraph.

LangGraph execution pipeline coordinating Planner, Formal Gate, and Environment nodes."""

from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from core.agent_state import AgentState
from core.cli_formatter import (
    UserPrompt,
    get_status_spinner,
    print_banner,
    print_divider,
    print_error,
    print_info,
    print_ready_prompt,
    print_session_end,
    print_step_update,
    print_success,
)
from core.config import UseCaseConfig, load_use_case
from core.environment_node import create_environment_node
from core.formal_gate_node import FormalGateNode, SubmitCallable
from core.mcp_utils import parse_mcp_response
from core.planner_node import create_planner_node, create_planner_router
from enforcement.contracts import DEFAULT_URL, STATE_TOOL, SUBMIT_TOOL
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

EXIT_COMMANDS = ("exit", "quit")
# The conversation of the chat is kept in memory under this thread, for the life of the process
CHAT_CONFIG = {"configurable": {"thread_id": "chat"}}

# ============================================================================
# ROUTERS
# ============================================================================

def gate_router(state: AgentState) -> str:
    """Routes after Formal Gate evaluation (replan rounds are bounded by the planner)."""
    verdict = state.get("guard_verdict")
    # The submit tool already executed the action: only reads reach the Environment
    if verdict == "BYPASS":
        return "environment"
    # BLOCKED goes back only for the final explanation (final_answer_only)
    if verdict in ("APPROVED", "SHIELDED", "REPLAN", "BLOCKED"):
        return "planner"
    return END

# ============================================================================
# GRAPH BUILDER
# ============================================================================

def _read_only_tools(tools: List[BaseTool]) -> List[BaseTool]:
    """Tools allowed to skip the Formal Gate: those with the MCP `readOnlyHint` annotation."""
    return [t for t in tools if (t.metadata or {}).get("readOnlyHint")]

def build_formal_gate_graph(
    llm,
    use_case: UseCaseConfig,
    environment_tools: List[BaseTool],
    submit_callable: SubmitCallable,
):
    """Builds the pipeline graph: Planner (LLM) -> Formal Gate -> Environment (reads only)."""
    read_only_tools = _read_only_tools(environment_tools)

    builder = StateGraph(AgentState)
    builder.add_node(
        "planner",
        create_planner_node(
            llm, environment_tools,
            max_steps=use_case.max_steps_per_turn, hints=use_case.planner_hints,
        ),
    )
    builder.add_node(
        "formal_gate",
        FormalGateNode(
            submit_callable=submit_callable,
            read_only_tools={t.name for t in read_only_tools},
        ),
    )
    builder.add_node("environment", create_environment_node(read_only_tools))

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", create_planner_router(use_case.max_steps_per_turn))
    builder.add_conditional_edges("formal_gate", gate_router)
    builder.add_edge("environment", "planner")

    return builder.compile(checkpointer=InMemorySaver())

# ============================================================================
# SETUP & LIFECYCLE MANAGERS
# ============================================================================

def _build_mcp_config(use_case: UseCaseConfig) -> Dict[str, Dict[str, Any]]:
    """Builds the stdio configuration of the use-case MCP server."""
    env_cmd, *env_args = use_case.environment_mcp_command
    return {
        "environment_server": {
            "command": env_cmd,
            "args": env_args,
            "transport": "stdio",
            "env": {"ASMETAS_URL": os.getenv("ASMETAS_URL", DEFAULT_URL)},
        },
    }

@asynccontextmanager
async def enforcement_session(use_case: UseCaseConfig):
    """ONE persistent session with the use-case server for the whole chat (fail-fast).

    The server keeps the live system and the enforcement state in memory, so it must
    not be restarted on every tool call (the default of MultiServerMCPClient.get_tools).
    """
    client = MultiServerMCPClient(_build_mcp_config(use_case))
    started = False
    try:
        async with client.session("environment_server") as mcp_session:
            environment_tools = await load_mcp_tools(mcp_session, server_name="environment_server")
            if SUBMIT_TOOL not in {t.name for t in environment_tools}:
                raise RuntimeError(f"Submit tool '{SUBMIT_TOOL}' missing from the use-case server.")
            if STATE_TOOL not in {t.name for t in _read_only_tools(environment_tools)}:
                raise RuntimeError(f"State tool '{STATE_TOOL}' missing or not declared read-only.")

            health = await mcp_session.call_tool(STATE_TOOL, {})
            health_data, health_raw = parse_mcp_response(
                [{"text": getattr(c, "text", "")} for c in health.content]
            )
            if health.isError or health_data.get("status") in ("recovery_required", "error"):
                raise RuntimeError(f"Enforcement server not ready: {health_data.get('reason', health_raw)}")
            print_success(f"Enforcement server ready ('{STATE_TOOL}' answered).")

            async def submit(args: Dict[str, Any]) -> tuple[bool, str]:
                result = await mcp_session.call_tool(SUBMIT_TOOL, args)
                text = "\n".join(getattr(c, "text", "") for c in result.content)
                return bool(result.isError), text

            started = True
            yield environment_tools, submit
    except Exception as e:
        if started or isinstance(e, RuntimeError):
            raise
        # A server that exits during startup (AsmetaS offline, model not loadable) closes the pipe
        cause = e
        while isinstance(cause, BaseExceptionGroup) and cause.exceptions:
            cause = cause.exceptions[0]
        raise RuntimeError(
            f"Use-case MCP server failed to start ({cause or type(cause).__name__});"
            " see its log above (AsmetaS unreachable or a model not loadable)."
        ) from e

# ============================================================================
# MAIN INTERACTIVE CLI
# ============================================================================

def _turn_input(user_input: str) -> AgentState:
    """Appends the user request to the conversation and resets every per-turn field."""
    return {
        "messages": [HumanMessage(content=user_input)],
        "candidate_action": None,
        "guard_verdict": None,
        "executed_action": None,
        "guard_feedback": None,
        "planner_steps": 0,
        "final_answer_only": False,
    }

async def main():
    print_banner()

    model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    print_info(f"Initializing LLM: [bold green]{model_name}[/bold green]")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)

    try:
        use_case_name = os.getenv("USE_CASE")
        use_case = load_use_case(use_case_name)
        print_info(f"Use case: [bold green]{use_case_name}[/bold green]")

        async with enforcement_session(use_case) as (environment_tools, submit_callable):
            graph = build_formal_gate_graph(llm, use_case, environment_tools, submit_callable)

            print_ready_prompt()
            prompt = UserPrompt()

            while True:
                try:
                    user_input = await prompt.read()
                    command = user_input.strip()
                    if not command:
                        continue
                    if command.lower() in EXIT_COMMANDS:
                        break

                    with get_status_spinner("Running agent..."):
                        async for step_output in graph.astream(_turn_input(user_input), CHAT_CONFIG):
                            print_step_update(step_output)

                    print_divider()
                except (KeyboardInterrupt, EOFError):
                    break
                except Exception as e:
                    print_error(f"Execution error: {e}")

    except Exception as err:
        print_error(f"Initialization or Session Error: {err}")
        sys.exit(1)
    finally:
        print_session_end()


if __name__ == "__main__":
    asyncio.run(main())
