"""The graph-based orchestrator for LangGraph.

LangGraph execution pipeline coordinating Planner, Formal Gate, and Environment nodes."""

from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph import END, START, StateGraph
from core.agent_state import AgentState
from core.cli_formatter import (
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
from core.config import (
    ASMETAS_MCP_COMMAND,
    UseCaseConfig,
    load_use_case,
)
from core.environment_node import create_environment_node
from core.formal_gate_node import FormalGateNode, SubmitCallable
from core.mcp_utils import parse_mcp_response
from core.planner_node import create_planner_node, create_planner_router
from enforcement.deploy import deploy
from enforcement.rest_client import AsmetaRestClient
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

EXIT_COMMANDS = ("exit", "quit")

# ============================================================================
# ROUTERS
# ============================================================================

def create_gate_router(policy: str, gate_mode: str = "sanitise"):
    """Routes after Formal Gate evaluation (replan rounds are bounded by the planner)."""

    def gate_router(state: AgentState) -> str:
        verdict = state.get("guard_verdict")

        if gate_mode == "submit":
            # The submit tool already executed the action: only reads reach the Environment
            if verdict == "BYPASS":
                return "environment"
            # BLOCKED goes back only for the final explanation (final_answer_only)
            if verdict in ("APPROVED", "SHIELDED", "REPLAN", "BLOCKED"):
                return "planner"
            return END

        if verdict in ("APPROVED", "BYPASS") or (
            verdict == "VIOLATION" and policy == "shielding"
        ):
            return "environment"
        if verdict == "VIOLATION":
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
    use_case: UseCaseConfig,
    environment_tools: List[BaseTool],
    sanitise_action_tool: Optional[Callable] = None,
    system_prompt: Optional[str] = None,
    extra_read_only_tools: Optional[List[str]] = None,
    submit_callable: Optional[SubmitCallable] = None,
):
    """Builds the pipeline graph: Planner (LLM) -> Formal Gate (AsmetaS) -> Environment."""
    builder = StateGraph(AgentState)
    builder.add_node(
        "planner",
        create_planner_node(
            llm, environment_tools, system_prompt,
            max_steps=use_case.max_steps_per_turn, hints=use_case.planner_hints,
        ),
    )
    builder.add_node(
        "formal_gate",
        FormalGateNode(
            sanitise_action_callable=sanitise_action_tool,
            policy=use_case.gate_policy,
            error_policy=use_case.error_policy,
            default_safe_action=use_case.default_safe_action,
            read_only_tools=_read_only_tool_names(environment_tools, extra_read_only_tools),
            action_mapping=use_case.action_mapping,
            default_monitored_vars=use_case.default_monitored_variables,
            gate_mode=use_case.gate_mode,
            submit_callable=submit_callable,
            submit_tool=use_case.submit_tool,
            submit_request_id_path=use_case.submit_request_id_path,
            decision_mapping=use_case.decision_mapping,
        ),
    )

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", create_planner_router(use_case.max_steps_per_turn))
    builder.add_conditional_edges(
        "formal_gate", create_gate_router(use_case.gate_policy, use_case.gate_mode)
    )

    if environment_tools:
        builder.add_node("environment", create_environment_node(environment_tools))
        builder.add_edge("environment", "planner")

    return builder.compile()

# ============================================================================
# SETUP & LIFECYCLE MANAGERS
# ============================================================================

def _build_mcp_config(use_case: UseCaseConfig) -> Dict[str, Dict[str, Any]]:
    """Builds the stdio configuration for the Environment and AsmetaS MCP servers.

    In submit mode the use-case server talks to AsmetaS itself: no adapter server.
    """
    env_cmd, *env_args = use_case.environment_mcp_command
    asmetas_url = os.getenv("ASMETAS_URL", "http://localhost:8080")
    config = {
        "environment_server": {
            "command": env_cmd,
            "args": env_args,
            "transport": "stdio",
            "env": {"ASMETAS_URL": asmetas_url},
        },
    }
    if use_case.gate_mode == "submit":
        return config

    asmetas_cmd, *asmetas_args = ASMETAS_MCP_COMMAND
    config["asmetas_server"] = {
        "command": asmetas_cmd,
        "args": asmetas_args,
        "transport": "stdio",
        "env": {
            "ASMETAS_URL": asmetas_url,
            "ASMETA_MODEL_NAME": use_case.asm_model_name,
        },
    }
    return config

def _deploy_asm_sources(use_case: UseCaseConfig) -> None:
    """Uploads the use case's ASM sources to AsmetaS (raises if unreachable or not retained)."""
    client = AsmetaRestClient(os.getenv("ASMETAS_URL", "http://localhost:8080"))
    try:
        deploy(client, list(use_case.asm_sources), [])
    finally:
        client.close()

async def _verify_asmetas_model(list_models_tool: BaseTool, model_name: str):
    """Verifies that the formal model is available on the AsmetaS web service."""
    models_data, models_raw = parse_mcp_response(await list_models_tool.ainvoke({}))

    if models_data.get("status") == "error":
        raise RuntimeError(
            f"AsmetaS web service unreachable: {models_data.get('message', models_raw)}"
        )

    if model_name not in models_data.get("models", []):
        raise RuntimeError(
            f"Formal model '{model_name}' is not present on AsmetaS"
            " server after the upload. Check `asm_sources` in the use case."
        )
    print_info(f"Model '{model_name}' confirmed on AsmetaS server.")

@asynccontextmanager
async def setup_mcp_and_enforcer_session(use_case: UseCaseConfig):
    """Context manager that starts the MCP servers and verifies the enforcer (fail-fast)."""
    setup = _submit_session if use_case.gate_mode == "submit" else _sanitise_session
    async with setup(use_case) as session:
        yield session

@asynccontextmanager
async def _submit_session(use_case: UseCaseConfig):
    """Submit mode: ONE persistent session with the use-case server for the whole chat.

    The server keeps the live system and the enforcement state in memory, so it must
    not be restarted on every tool call (the default of MultiServerMCPClient.get_tools).
    """
    client = MultiServerMCPClient(_build_mcp_config(use_case))
    started = False
    try:
        async with client.session("environment_server") as mcp_session:
            environment_tools = await load_mcp_tools(mcp_session, server_name="environment_server")
            tool_names = {t.name for t in environment_tools}
            if use_case.submit_tool not in tool_names:
                raise RuntimeError(f"Submit tool '{use_case.submit_tool}' missing from the use-case server.")
            if use_case.health_tool not in _read_only_tool_names(environment_tools):
                raise RuntimeError(f"Health tool '{use_case.health_tool}' missing or not declared read-only.")

            health = await mcp_session.call_tool(use_case.health_tool, {})
            health_data, health_raw = parse_mcp_response(
                [{"text": getattr(c, "text", "")} for c in health.content]
            )
            if health.isError or health_data.get("status") in ("recovery_required", "error"):
                raise RuntimeError(f"Enforcement server not ready: {health_data.get('reason', health_raw)}")
            print_success(f"Enforcement server ready ('{use_case.health_tool}' answered).")

            async def submit(args: Dict[str, Any]) -> tuple[bool, str]:
                result = await mcp_session.call_tool(use_case.submit_tool, args)
                text = "\n".join(getattr(c, "text", "") for c in result.content)
                return bool(result.isError), text

            started = True
            yield {"environment_tools": environment_tools, "submit_callable": submit}
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

@asynccontextmanager
async def _sanitise_session(use_case: UseCaseConfig):
    """Sanitise mode: AsmetaS adapter server + environment server, enforcer session started here."""
    model_name = use_case.asm_model_name
    client = MultiServerMCPClient(_build_mcp_config(use_case))

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
    list_models_tool = tools_by_name.get("list_models")
    stop_tool = tools_by_name.get("stop_enforcer")

    if not sanitise_tool or not start_tool or not list_models_tool:
        raise RuntimeError(
            "Essential Formal Gate tools (sanitise_action, start_enforcer, list_models) missing from server."
        )

    _deploy_asm_sources(use_case)
    await _verify_asmetas_model(list_models_tool, model_name)

    init_data, _ = parse_mcp_response(await start_tool.ainvoke({"asm_name": model_name}))
    if init_data.get("status") == "error":
        raise RuntimeError(
            f"Failed to start AsmetaS Enforcer session: {init_data.get('message')}"
        )

    print_success(
        f"AsmetaS enforcer session active for '{model_name}' (ID:"
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
        "guard_verdict": None,
        "sanitised_action": None,
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

        async with setup_mcp_and_enforcer_session(use_case) as session:
            graph = build_formal_gate_graph(
                llm=llm,
                use_case=use_case,
                environment_tools=session["environment_tools"],
                sanitise_action_tool=session.get("sanitise_tool"),
                extra_read_only_tools=_read_only_tools_from_env(),
                submit_callable=session.get("submit_callable"),
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
