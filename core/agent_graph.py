"""The graph-based orchestrator for LangGraph.

LangGraph execution pipeline coordinating the Planner and Formal Gate nodes.

READING GUIDE (startup to answer):
    main() -> load_use_case(USE_CASE) -> enforcement_session()   [fail-fast checks]
           -> build_formal_gate_graph() -> CLI loop, one graph run per user message.
Graph, for each message:

    START -> planner --(tool call)--> formal_gate --(verdict)--> planner ... -> END
    planner --(plain text answer, no tool call)-------------------------> END

The planner (LLM) proposes tool calls; the formal gate runs read-only tools directly and
sends `submit_plan` to the use-case MCP server, which verifies it with the ASM models.
Nothing in this file knows any domain: it all comes from `UseCaseConfig`.
"""

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
from core.formal_gate_node import FormalGateNode, SubmitCallable, parse_mcp_response
from core.planner_node import create_planner_node, create_planner_router
from enforcement.contracts import STATE_TOOL, SUBMIT_TOOL
load_dotenv()  # reads .env (GEMINI_API_KEY, GEMINI_MODEL, USE_CASE, ASMETAS_URL)
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
    """Routes after Formal Gate evaluation (replan rounds are bounded by the planner).

    Every verdict except ERROR returns to the planner: it needs the tool result to continue
    or to write the final answer. ERROR (operational failure) ends the turn at once."""
    # BLOCK goes back only for the final explanation (final_answer_only)
    if state.get("guard_verdict") in ("BYPASS", "ALLOW", "REPLACE", "REPLAN", "BLOCK"):
        return "planner"
    return END

# ============================================================================
# GRAPH BUILDER
# ============================================================================

def _result_text(result: Any) -> str:
    """Text of an MCP tool result."""
    return "\n".join(getattr(c, "text", "") for c in result.content)

def _read_only_tools(tools: List[BaseTool]) -> List[BaseTool]:
    """Tools allowed to skip the Formal Gate: those with the MCP `readOnlyHint` annotation."""
    return [t for t in tools if (t.metadata or {}).get("readOnlyHint")]

def build_formal_gate_graph(
    llm,
    use_case: UseCaseConfig,
    server_tools: List[BaseTool],
    submit_callable: SubmitCallable,
):
    """Builds the pipeline graph: Planner (LLM) <-> Formal Gate.

    `server_tools` are the MCP tools discovered on the use-case server; the planner sees all
    of them, the gate runs directly only those marked read-only. `submit_callable` is how the
    gate reaches `submit_plan` on the persistent MCP session. The `InMemorySaver` keeps the
    conversation between messages for the whole process lifetime."""
    builder = StateGraph(AgentState)
    builder.add_node(
        "planner",
        create_planner_node(
            llm, server_tools, use_case.max_steps_per_turn, use_case.planner_hints,
        ),
    )
    builder.add_node(
        "formal_gate",
        FormalGateNode(
            submit_callable=submit_callable,
            read_only_tools=_read_only_tools(server_tools),
        ),
    )

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", create_planner_router(use_case.max_steps_per_turn))
    builder.add_conditional_edges("formal_gate", gate_router)

    return builder.compile(checkpointer=InMemorySaver())

# ============================================================================
# SETUP & LIFECYCLE MANAGERS
# ============================================================================

def _build_mcp_config(use_case: UseCaseConfig) -> Dict[str, Dict[str, Any]]:
    """Builds the stdio configuration of the use-case MCP server.

    The server is a child process and inherits only basic system variables plus the ones
    listed in `env` here: a variable set in the agent's .env does NOT reach it unless added
    to this dict (as done for ASMETAS_URL). Add use-case variables here if a server needs them."""
    env_cmd, *env_args = use_case.mcp_server_command
    # ASMETAS_URL (from .env) is the only source of the AsmetaS address
    asmeta_url = os.getenv("ASMETAS_URL")
    if not asmeta_url:
        raise RuntimeError("ASMETAS_URL is not set (see .env.example).")
    return {
        "use_case_server": {
            "command": env_cmd,
            "args": env_args,
            "transport": "stdio",
            "env": {"ASMETAS_URL": asmeta_url},
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
        async with client.session("use_case_server") as mcp_session:
            server_tools = await load_mcp_tools(mcp_session, server_name="use_case_server")
            # Startup checks (fail-fast): the server must expose the two contract tools,
            # and the state tool must be read-only so the gate may call it directly.
            if SUBMIT_TOOL not in {t.name for t in server_tools}:
                raise RuntimeError(f"Submit tool '{SUBMIT_TOOL}' missing from the use-case server.")
            if STATE_TOOL not in {t.name for t in _read_only_tools(server_tools)}:
                raise RuntimeError(f"State tool '{STATE_TOOL}' missing or not declared read-only.")

            # Availability check: a real read of the live system through the whole chain
            health = await mcp_session.call_tool(STATE_TOOL, {})
            health_raw = _result_text(health)
            health_data = parse_mcp_response(health_raw)
            # An empty or non-JSON answer is not a state: the gate must not start on it
            if health.isError or not health_data or health_data.get("status") in ("recovery_required", "error"):
                raise RuntimeError(f"Enforcement server not ready: {health_data.get('reason', health_raw or 'empty answer')}")
            print_success(f"Enforcement server ready ('{STATE_TOOL}' answered).")

            async def submit(args: Dict[str, Any]) -> tuple[bool, str]:
                """Calls `submit_plan`; returns (is_error, raw text) for the Formal Gate to interpret."""
                result = await mcp_session.call_tool(SUBMIT_TOOL, args)
                return bool(result.isError), _result_text(result)

            started = True  # from now on errors are session errors, not startup errors
            yield server_tools, submit
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
        "guard_verdict": None,
        "guard_feedback": None,
        "planner_steps": 0,
        "final_answer_only": False,
    }

async def main():
    """Interactive entry point: any startup failure prints the error and exits with code 1
    BEFORE the `You:` prompt appears."""
    print_banner()

    try:
        # GEMINI_MODEL (from .env) is required: there is no default model
        model_name = os.getenv("GEMINI_MODEL")
        if not model_name:
            raise RuntimeError("GEMINI_MODEL is not set (see .env.example).")
        print_info(f"Initializing LLM: [bold green]{model_name}[/bold green]")
        llm = ChatGoogleGenerativeAI(model=model_name)

        use_case_name = os.getenv("USE_CASE")
        use_case = load_use_case(use_case_name)
        print_info(f"Use case: [bold green]{use_case_name}[/bold green]")

        async with enforcement_session(use_case) as (server_tools, submit_callable):
            graph = build_formal_gate_graph(llm, use_case, server_tools, submit_callable)

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

                    # One graph run per user message; each node update is printed as it happens
                    with get_status_spinner("Running agent..."):
                        async for step_output in graph.astream(_turn_input(user_input), CHAT_CONFIG):
                            print_step_update(step_output)

                    print_divider()
                except (KeyboardInterrupt, EOFError):
                    break
                except Exception as e:
                    # An error inside a turn (e.g. LLM API) must not kill the chat
                    print_error(f"Execution error: {e}")

    except Exception as err:
        print_error(f"Initialization or Session Error: {err}")
        sys.exit(1)
    finally:
        print_session_end()


if __name__ == "__main__":
    asyncio.run(main())
