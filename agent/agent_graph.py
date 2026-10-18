"""The graph-based orchestrator for LangGraph.

LangGraph execution pipeline coordinating Planner, Formal Gate, and Environment nodes."""

from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Literal, Optional
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from agent.agent_state import AgentState
from agent.cli_formatter import (
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
from agent.config import (
    ACTION_MAPPING,
    ASMETA_MODEL_NAME,
    ASMETAS_MCP_COMMAND,
    DEFAULT_MONITORED_VARIABLES,
    DEFAULT_SAFE_ACTION,
    ENVIRONMENT_MCP_COMMAND,
    ERROR_POLICY,
    GATE_POLICY,
    MAX_RETRIES,
)
from agent.environment_node import create_environment_node
from agent.formal_gate_node import FormalGateNode
from agent.mcp_utils import parse_mcp_response
from agent.planner_node import create_planner_node, planner_router
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

EXIT_COMMANDS = ("exit", "quit")

# ============================================================================
# ROUTERS
# ============================================================================

def create_gate_router(policy: str, max_retries: int = 3):
    """Routes after Formal Gate evaluation."""

    def gate_router(state: AgentState) -> str:
        verdict = state.get("guard_verdict")

        if verdict in ("APPROVED", "BYPASS") or (
            verdict == "VIOLATION" and policy == "shielding"
        ):
            return "environment"
        if verdict == "VIOLATION" and state.get("retry_count", 0) < max_retries:
            return "planner"
        return END

    return gate_router

# ============================================================================
# GRAPH BUILDER
# ============================================================================

def _read_only_tool_names(
    tools: List[BaseTool], extra: Optional[List[str]] = None
) -> set[str]:
    """Tools allowed to skip the Formal Gate: MCP `readOnlyHint` annotation or explicit override."""
    annotated = {t.name for t in tools if (t.metadata or {}).get("readOnlyHint")}
    return annotated | set(extra or ())

def build_formal_gate_graph(
    llm,
    environment_tools: List[BaseTool],
    sanitise_action_tool: Optional[Callable],
    policy: Literal["shielding", "replan"],
    error_policy: Literal["fail_stop", "fail_safe"],
    default_safe_action: str,
    system_prompt: Optional[str],
    max_retries: int,
    action_mapping: Optional[Dict[str, str]],
    default_monitored_vars: Optional[Dict[str, str]],
    extra_read_only_tools: Optional[List[str]] = None,
):
    """Builds the pipeline graph: Planner (LLM) -> Formal Gate (AsmetaS) -> Environment."""
    builder = StateGraph(AgentState)
    builder.add_node("planner", create_planner_node(llm, environment_tools, system_prompt))
    builder.add_node(
        "formal_gate",
        FormalGateNode(
            sanitise_action_callable=sanitise_action_tool,
            policy=policy,
            error_policy=error_policy,
            default_safe_action=default_safe_action,
            read_only_tools=_read_only_tool_names(environment_tools, extra_read_only_tools),
            action_mapping=action_mapping,
            default_monitored_vars=default_monitored_vars,
        ),
    )

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", planner_router)
    builder.add_conditional_edges("formal_gate", create_gate_router(policy, max_retries))

    if environment_tools:
        builder.add_node("environment", create_environment_node(environment_tools))
        builder.add_edge("environment", "planner")

    return builder.compile()

# ============================================================================
# SETUP & LIFECYCLE MANAGERS
# ============================================================================

def _build_mcp_config() -> Dict[str, Dict[str, Any]]:
    """Builds the stdio configuration for the Environment and AsmetaS MCP servers."""
    env_cmd, *env_args = ENVIRONMENT_MCP_COMMAND
    asmetas_cmd, *asmetas_args = ASMETAS_MCP_COMMAND
    return {
        "environment_server": {
            "command": env_cmd,
            "args": env_args,
            "transport": "stdio",
        },
        "asmetas_server": {
            "command": asmetas_cmd,
            "args": asmetas_args,
            "transport": "stdio",
            "env": {
                "ASMETAS_URL": os.getenv("ASMETAS_URL", "http://localhost:8080"),
                "ASMETA_MODEL_NAME": ASMETA_MODEL_NAME,
            },
        },
    }

async def _verify_asmetas_model(list_models_tool: Optional[BaseTool]):
    """Verifies that the formal model is already available on the AsmetaS web service."""
    if not list_models_tool:
        return

    models_data, models_raw = parse_mcp_response(await list_models_tool.ainvoke({}))

    if models_data.get("status") == "error":
        raise RuntimeError(
            f"AsmetaS web service unreachable: {models_data.get('message', models_raw)}"
        )

    if ASMETA_MODEL_NAME not in models_data.get("models", []):
        raise RuntimeError(
            f"Formal model '{ASMETA_MODEL_NAME}' is not present on AsmetaS"
            " server. Load it on the web service before starting the agent."
        )
    print_info(f"Model '{ASMETA_MODEL_NAME}' confirmed on AsmetaS server.")

@asynccontextmanager
async def setup_mcp_and_enforcer_session():
    """Context manager to initialize MCP servers, start AsmetaS enforcer,

    and handle cleanup gracefully on exit.
    """
    client = MultiServerMCPClient(_build_mcp_config())

    # Retrieve Tools from MCP Servers
    try:
        asmetas_tools = await client.get_tools(server_name="asmetas_server")
        environment_tools = await client.get_tools(server_name="environment_server")
    except Exception as e:
        print_error(f"Failed to connect to MCP servers: {e}")
        raise

    # Model Check & Enforcer Session Start
    tools_by_name = {t.name: t for t in asmetas_tools}
    sanitise_tool = tools_by_name.get("sanitise_action")
    start_tool = tools_by_name.get("start_enforcer")
    stop_tool = tools_by_name.get("stop_enforcer")

    if not sanitise_tool or not start_tool:
        raise RuntimeError(
            "Essential Formal Gate tools (sanitise_action, start_enforcer) missing from server."
        )

    await _verify_asmetas_model(tools_by_name.get("list_models"))

    init_data, _ = parse_mcp_response(
        await start_tool.ainvoke({"asm_name": ASMETA_MODEL_NAME})
    )
    if init_data.get("status") == "error":
        raise RuntimeError(
            f"Failed to start AsmetaS Enforcer session: {init_data.get('message')}"
        )

    print_success(
        f"AsmetaS enforcer session active for '{ASMETA_MODEL_NAME}' (ID:"
        f" {init_data.get('execution_id', 'OK')})"
    )

    try:
        yield {
            "environment_tools": environment_tools,
            "sanitise_tool": sanitise_tool,
        }
    finally:
        if stop_tool:
            try:
                await stop_tool.ainvoke({})
            except Exception:
                pass

# ============================================================================
# MAIN INTERACTIVE CLI
# ============================================================================

def _read_only_tools_from_env() -> List[str]:
    """Parses the optional comma-separated READ_ONLY_TOOLS override (for unannotated tools)."""
    return [t.strip() for t in os.getenv("READ_ONLY_TOOLS", "").split(",") if t.strip()]

def _initial_state(user_input: str) -> AgentState:
    """Builds a fresh per-turn graph state for the given user request."""
    return {
        "messages": [HumanMessage(content=user_input)],
        "candidate_action": None,
        "monitored_variables": {},
        "guard_verdict": None,
        "sanitised_action": None,
        "guard_feedback": None,
        "retry_count": 0,
        "max_retries": MAX_RETRIES,
        "execution_id": None,
        "action_history": [],
    }

async def main():
    print_banner()

    model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    print_info(f"Initializing LLM: [bold green]{model_name}[/bold green]")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)

    try:
        async with setup_mcp_and_enforcer_session() as session:
            graph = build_formal_gate_graph(
                llm=llm,
                environment_tools=session["environment_tools"],
                sanitise_action_tool=session["sanitise_tool"],
                policy=GATE_POLICY,
                error_policy=ERROR_POLICY,
                default_safe_action=DEFAULT_SAFE_ACTION,
                system_prompt=os.getenv("SYSTEM_PROMPT"),
                max_retries=MAX_RETRIES,
                action_mapping=dict(ACTION_MAPPING),
                default_monitored_vars=dict(DEFAULT_MONITORED_VARIABLES),
                extra_read_only_tools=_read_only_tools_from_env(),
            )

            print_ready_prompt()

            while True:
                try:
                    user_input = input("\nYou: ")
                    command = user_input.strip()
                    if not command:
                        continue
                    if command.lower() in EXIT_COMMANDS:
                        break

                    with get_status_spinner("Running agent..."):
                        async for step_output in graph.astream(_initial_state(user_input)):
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
