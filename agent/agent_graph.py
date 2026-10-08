"""
Complete LangGraph Formal Gate Graph implementation.
Coordinates Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action).
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph

from agent.agent_card import AgentCard, load_agent_card
from agent.agent_state import AgentState
from agent.environment_node import create_environment_node
from agent.formal_gate_node import FormalGateNode
from agent.planner_node import create_planner_node, planner_router
from agent.cli_formatter import (
    console,
    print_banner,
    print_info,
    print_warning,
    print_error,
    print_success,
    print_ready_prompt,
    print_divider,
    print_session_end,
    print_step_update,
    get_status_spinner,
)

# Load environment
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()


def create_gate_router(policy: str, max_retries: int = 3):
    """
    Routes after Formal Gate evaluation.
    """
    def gate_router(state: AgentState) -> str:
        verdict = state.get("guard_verdict")

        if verdict == "APPROVED" or (verdict == "VIOLATION" and policy == "shielding"):
            # Safe to execute in environment
            return "environment"
        elif verdict == "VIOLATION":
            # Re-planning policy
            retry_count = state.get("retry_count", 0)
            if retry_count < max_retries:
                return "planner"
            return END
        elif verdict == "ERROR":
            return END
        elif verdict == "BYPASS":
            return "environment"

        return END

    return gate_router


def build_formal_gate_graph(
    llm,
    environment_tools: List[BaseTool],
    sanitise_action_tool: Optional[Callable] = None,
    policy: Literal["shielding", "replan"] = "shielding",
    error_policy: Literal["fail_stop", "fail_safe"] = "fail_stop",
    system_prompt: Optional[str] = None,
    max_retries: int = 3,
    agent_card: Optional[AgentCard] = None,
    action_mapping: Optional[Dict[str, str]] = None,
    default_monitored_vars: Optional[Dict[str, str]] = None,
    monitored_tools: Optional[List[str]] = None,
):
    """
    Builds the pipeline graph:
    Planner (LLM) -> Formal Gate (AsmetaS) -> Environment (Action execution).
    """
    planner = create_planner_node(llm, environment_tools, system_prompt)
    formal_gate = FormalGateNode(
        sanitise_action_callable=sanitise_action_tool,
        policy=policy,
        error_policy=error_policy,
        monitored_tools=monitored_tools,
        agent_card=agent_card,
        action_mapping=action_mapping,
        default_monitored_vars=default_monitored_vars,
    )
    environment = create_environment_node(environment_tools) if environment_tools else None

    # Graph structure
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("formal_gate", formal_gate)
    if environment:
        builder.add_node("environment", environment)

    # Execution flow and conditional routing
    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", planner_router)
    builder.add_conditional_edges("formal_gate", create_gate_router(policy, max_retries))

    if environment:
        # Loop back to planner so it can summarize execution outcome
        builder.add_edge("environment", "planner")

    return builder.compile()


def parse_mcp_response(res: Any) -> tuple[dict, str]:
    """
    Parses MCP tool output into (data_dict, raw_text).
    Handles string JSON, dicts, or lists of content blocks returned by langchain_mcp_adapters.
    """
    raw_text = ""
    if isinstance(res, list) and len(res) > 0:
        first_item = res[0]
        if isinstance(first_item, dict) and "text" in first_item:
            raw_text = str(first_item["text"])
        elif hasattr(first_item, "text"):
            raw_text = str(first_item.text)
        elif isinstance(first_item, str):
            raw_text = first_item
        else:
            raw_text = str(first_item)
    elif isinstance(res, dict):
        return res, json.dumps(res)
    elif isinstance(res, str):
        raw_text = res
    else:
        raw_text = str(res)

    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data, raw_text
    except Exception:
        pass
    return {}, raw_text


async def main():
    """
    Interactive CLI runner for the Formal Gate Agent.
    """
    print_banner()

    # Initialize planner model
    model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    print_info(f"Initializing LLM: [bold green]{model_name}[/bold green]")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.0,
    )

    # Load AsmetaS guard agent-card contract
    guard_card_path = os.getenv("GUARD_AGENT_CARD_PATH", "mcp_server/asmetas/agent-card.json")
    asmetas_card = load_agent_card(guard_card_path)
    print_info(
        f"Loaded guard card: [bold magenta]{asmetas_card.name}[/bold magenta] "
        f"({asmetas_card.type}, {asmetas_card.protocol}/{asmetas_card.transport})"
    )

    # Load environment agent card (or fallback to direct command configuration)
    env_card_path = os.getenv("ENVIRONMENT_AGENT_CARD_PATH", "mcp_server/vehicle/agent-card.json")
    env_card = None
    if Path(env_card_path).is_file():
        env_card = load_agent_card(env_card_path)
        print_info(
            f"Loaded environment card: [bold cyan]{env_card.name}[/bold cyan] "
            f"({env_card.type}, {env_card.protocol}/{env_card.transport})"
        )
        env_server_config = env_card.to_mcp_server_config()
    else:
        env_cmd = os.getenv("ENVIRONMENT_MCP_COMMAND", "python")
        env_args = os.getenv("ENVIRONMENT_MCP_ARGS", "mcp_server/vehicle/vehicle_mcp_server.py").split()
        env_server_config = {
            "command": env_cmd,
            "args": env_args,
            "transport": "stdio",
        }
        print_info(f"Configured environment server: [bold cyan]{env_cmd} {' '.join(env_args)}[/bold cyan]")

    # Start MCP clients based on agent card configs
    print_info("Connecting to MCP servers...")
    asmetas_env = {"ASMETAS_URL": os.getenv("ASMETAS_URL", "http://localhost:8080")}
    mcp_config = {
        "environment_server": env_server_config,
        "asmetas_server": asmetas_card.to_mcp_server_config(env=asmetas_env),
    }

    client = MultiServerMCPClient(mcp_config)

    # Fetch tools from servers
    try:
        asmetas_tools = await client.get_tools(server_name="asmetas_server")
    except Exception as e:
        print_error(f"Failed to connect to AsmetaS MCP server: {e}")
        print_error("AsmetaS formal service is not available. Chat will NOT be started.")
        sys.exit(1)

    try:
        environment_tools = await client.get_tools(server_name="environment_server")
    except Exception as e:
        print_error(f"Failed to connect to Environment server: {e}")
        print_error("Chat will NOT be started.")
        sys.exit(1)

    # Validate MCP server tools against declared Agent Card skills
    missing_guard_skills = asmetas_card.validate_mcp_tools(asmetas_tools)
    if missing_guard_skills:
        print_error(f"Missing required skills in AsmetaS server contract: {missing_guard_skills}")
        print_error("AsmetaS server does not satisfy the A2A contract. Chat will NOT be started.")
        sys.exit(1)
    else:
        print_success(f"[A2A] Verified {len(asmetas_card.skills)} skills for '{asmetas_card.name}' contract.")

    if env_card:
        missing_env_skills = env_card.validate_mcp_tools(environment_tools)
        if missing_env_skills:
            print_warning(f"Missing skills in Environment server: {missing_env_skills}")
        else:
            print_success(f"[A2A] Verified {len(env_card.skills)} skills for '{env_card.name}' contract.")

    print_info(f"Environment tools: {[t.name for t in environment_tools]}")
    print_info(f"Formal guard tools: {[t.name for t in asmetas_tools]}")

    # Resolve AsmetaS tools needed by the formal gate
    sanitise_tool = next((t for t in asmetas_tools if t.name == "sanitise_action"), None)
    start_tool = next((t for t in asmetas_tools if t.name == "start_enforcer"), None)
    stop_tool = next((t for t in asmetas_tools if t.name == "stop_enforcer"), None)
    list_models_tool = next((t for t in asmetas_tools if t.name == "list_models"), None)
    upload_model_tool = next((t for t in asmetas_tools if t.name == "upload_model"), None)

    if not sanitise_tool or not start_tool:
        print_error("Essential Formal Gate tools (sanitise_action, start_enforcer) are missing.")
        print_error("AsmetaS formal service is not available. Chat will NOT be started.")
        sys.exit(1)

    asm_model_name = os.getenv("ASMETA_MODEL_NAME", "SafetyEnforcerModel.asm")
    default_model_path = os.getenv("ASMETA_MODEL_PATH")

    # Check that model exists on AsmetaS and service is reachable
    if list_models_tool:
        try:
            models_info_raw = await list_models_tool.ainvoke({})
            models_data, models_raw = parse_mcp_response(models_info_raw)
            if models_data.get("status") == "error":
                err_msg = models_data.get("message", models_raw)
                print_error(f"AsmetaS web service unreachable: {err_msg}")
                print_error("AsmetaS formal service is not available. Chat will NOT be started.")
                sys.exit(1)

            server_models = models_data.get("models", []) if isinstance(models_data, dict) else []
            if asm_model_name not in server_models:
                uploaded = False
                if upload_model_tool and default_model_path and Path(default_model_path).is_file():
                    print_info(f"Model '{asm_model_name}' not found on AsmetaS. Uploading from {default_model_path}...")
                    upload_res_raw = await upload_model_tool.ainvoke({"model_path": default_model_path})
                    upload_data, upload_raw = parse_mcp_response(upload_res_raw)
                    if upload_data.get("status") == "success":
                        print_success(f"Model '{asm_model_name}' uploaded successfully to AsmetaS.")
                        uploaded = True
                    else:
                        print_warning(f"Upload failed: {upload_data.get('message', upload_raw)}")

                if not uploaded:
                    print_error(f"Formal model '{asm_model_name}' is not present on AsmetaS server.")
                    print_error("Make sure the model resides in AsmetaS-web-service. Chat will NOT be started.")
                    sys.exit(1)
            else:
                print_info(f"Model '{asm_model_name}' confirmed on AsmetaS server.")
        except Exception as e:
            print_error(f"Connection to AsmetaS-web-service failed: {e}")
            print_error("AsmetaS formal service is not available. Chat will NOT be started.")
            sys.exit(1)

    # Start enforcer session on AsmetaS (fail-fast if unreachable)
    try:
        init_res_raw = await start_tool.ainvoke({"asm_name": asm_model_name})
        init_data, init_raw = parse_mcp_response(init_res_raw)
        if init_data.get("status") == "error":
            err_msg = init_data.get("message", init_raw)
            print_error(f"Failed to start AsmetaS Enforcer session: {err_msg}")
            print_error("AsmetaS formal service is not available. Chat will NOT be started.")
            sys.exit(1)

        exec_id = init_data.get("execution_id", "OK")
        print_success(f"AsmetaS enforcer ready for '{asm_model_name}' (session ID: {exec_id})")
    except Exception as e:
        print_error(f"AsmetaS Enforcer startup failed: {e}")
        print_error("AsmetaS formal service is not available. Chat will NOT be started.")
        sys.exit(1)

    # Action mapping and default monitored variables
    action_mapping_raw = os.getenv("ACTION_MAPPING", '{"KEEP": "IDLE"}')
    try:
        action_mapping = json.loads(action_mapping_raw) if action_mapping_raw else {}
    except Exception:
        action_mapping = {}

    default_monitored_raw = os.getenv("DEFAULT_MONITORED_VARIABLES", '{"rightLaneFree": "false"}')
    try:
        default_monitored_vars = json.loads(default_monitored_raw) if default_monitored_raw else {}
    except Exception:
        default_monitored_vars = {}

    monitored_tools_env = os.getenv("MONITORED_TOOLS")
    monitored_tools = (
        [t.strip() for t in monitored_tools_env.split(",") if t.strip()]
        if monitored_tools_env
        else None
    )

    system_prompt = os.getenv("SYSTEM_PROMPT")

    graph = build_formal_gate_graph(
        llm=llm,
        environment_tools=environment_tools,
        sanitise_action_tool=sanitise_tool,
        policy="shielding",
        error_policy="fail_safe",
        system_prompt=system_prompt,
        max_retries=3,
        agent_card=asmetas_card,
        action_mapping=action_mapping,
        default_monitored_vars=default_monitored_vars,
        monitored_tools=monitored_tools,
    )

    print_ready_prompt()

    try:
        while True:
            try:
                user_input = input("\nYou: ")
                if not user_input.strip():
                    continue
                if user_input.strip().lower() in ["exit", "quit"]:
                    break

                initial_state = {
                    "messages": [HumanMessage(content=user_input)],
                    "candidate_action": None,
                    "monitored_variables": {},
                    "guard_verdict": None,
                    "sanitised_action": None,
                    "guard_feedback": None,
                    "retry_count": 0,
                    "max_retries": 3,
                    "execution_id": None,
                    "action_history": [],
                }

                with get_status_spinner("Running agent..."):
                    async for step_output in graph.astream(initial_state):
                        print_step_update(step_output)

                print_divider()
            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                print_error(f"Execution error: {e}")
    finally:
        if stop_tool:
            try:
                await stop_tool.ainvoke({})
            except Exception:
                pass
        print_session_end()


if __name__ == "__main__":
    asyncio.run(main())

