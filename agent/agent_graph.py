"""Complete LangGraph Formal Gate Graph implementation.
Coordinates Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action).
"""

from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
import sys
import time
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
from agent.cli_formatter import (
    console,
    get_status_spinner,
    print_banner,
    print_divider,
    print_error,
    print_info,
    print_ready_prompt,
    print_session_end,
    print_step_update,
    print_success,
    print_warning,
)
from agent.config import (
    ACTION_MAPPING,
    ASMETA_MODEL_NAME,
    DEFAULT_ENVIRONMENT_COMMAND,
    DEFAULT_MONITORED_VARIABLES,
    DEFAULT_SAFE_ACTION,
    ENVIRONMENT_AGENT_CARD_PATH,
    ERROR_POLICY,
    GATE_POLICY,
    GUARD_AGENT_CARD_PATH,
    MAX_RETRIES,
)
from agent.environment_node import create_environment_node
from agent.formal_gate_node import FormalGateNode
from agent.planner_node import create_planner_node, planner_router

# Load environment
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
  time.tzset()


# ============================================================================
# HELPER FUNCTIONS & ROUTERS
# ============================================================================

def parse_mcp_response(res: Any) -> tuple[dict, str]:
  """Parses MCP tool output into (data_dict, raw_text)."""
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


def create_gate_router(policy: str, max_retries: int = 3):
  """Routes after Formal Gate evaluation."""

  def gate_router(state: AgentState) -> str:
    verdict = state.get("guard_verdict")

    if verdict == "APPROVED" or (
        verdict == "VIOLATION" and policy == "shielding"
    ):
      return "environment"
    elif verdict == "VIOLATION":
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


# ============================================================================
# GRAPH BUILDER
# ============================================================================

def build_formal_gate_graph(
    llm,
    environment_tools: List[BaseTool],
    sanitise_action_tool: Optional[Callable],
    policy: Literal["shielding", "replan"],
    error_policy: Literal["fail_stop", "fail_safe"],
    default_safe_action: str,
    system_prompt: Optional[str],
    max_retries: int,
    agent_card: Optional[AgentCard],
    action_mapping: Optional[Dict[str, str]],
    default_monitored_vars: Optional[Dict[str, str]],
    monitored_tools: Optional[List[str]],
):
  """Builds the pipeline graph: Planner (LLM) -> Formal Gate (AsmetaS) -> Environment."""
  planner = create_planner_node(llm, environment_tools, system_prompt)
  formal_gate = FormalGateNode(
      sanitise_action_callable=sanitise_action_tool,
      policy=policy,
      error_policy=error_policy,
      default_safe_action=default_safe_action,
      monitored_tools=monitored_tools,
      agent_card=agent_card,
      action_mapping=action_mapping,
      default_monitored_vars=default_monitored_vars,
  )
  environment = (
      create_environment_node(environment_tools) if environment_tools else None
  )

  builder = StateGraph(AgentState)
  builder.add_node("planner", planner)
  builder.add_node("formal_gate", formal_gate)
  if environment:
    builder.add_node("environment", environment)

  builder.add_edge(START, "planner")
  builder.add_conditional_edges("planner", planner_router)
  builder.add_conditional_edges(
      "formal_gate", create_gate_router(policy, max_retries)
  )

  if environment:
    builder.add_edge("environment", "planner")

  return builder.compile()


# ============================================================================
# SETUP & LIFECYCLE MANAGERS
# ============================================================================

async def _verify_and_prepare_asmetas_model(asmetas_tools: List[BaseTool]):
  """Verifies model presence on AsmetaS web service and uploads it if missing."""
  list_models_tool = next(
      (t for t in asmetas_tools if t.name == "list_models"), None
  )
  upload_model_tool = next(
      (t for t in asmetas_tools if t.name == "upload_model"), None
  )
  default_model_path = os.getenv("ASMETA_MODEL_PATH")

  if not list_models_tool:
    return

  models_info_raw = await list_models_tool.ainvoke({})
  models_data, models_raw = parse_mcp_response(models_info_raw)

  if models_data.get("status") == "error":
    raise RuntimeError(
        f"AsmetaS web service unreachable: {models_data.get('message', models_raw)}"
    )

  server_models = (
      models_data.get("models", []) if isinstance(models_data, dict) else []
  )
  if ASMETA_MODEL_NAME not in server_models:
    uploaded = False
    if (
        upload_model_tool
        and default_model_path
        and Path(default_model_path).is_file()
    ):
      print_info(
          f"Model '{ASMETA_MODEL_NAME}' missing on server. Uploading from"
          f" {default_model_path}..."
      )
      upload_res_raw = await upload_model_tool.ainvoke(
          {"model_path": default_model_path}
      )
      upload_data, upload_raw = parse_mcp_response(upload_res_raw)
      if upload_data.get("status") == "success":
        print_success(
            f"Model '{ASMETA_MODEL_NAME}' uploaded successfully to AsmetaS."
        )
        uploaded = True

    if not uploaded:
      raise RuntimeError(
          f"Formal model '{ASMETA_MODEL_NAME}' is not present on AsmetaS"
          " server."
      )
  else:
    print_info(f"Model '{ASMETA_MODEL_NAME}' confirmed on AsmetaS server.")


@asynccontextmanager
async def setup_mcp_and_enforcer_session():
  """Context manager to initialize MCP servers, validate contracts, start AsmetaS enforcer,

  and handle cleanup gracefully on exit.
  """
  # Load Agent Cards & Server Configs
  asmetas_card = load_agent_card(GUARD_AGENT_CARD_PATH)
  print_info(
      f"Loaded guard card: [bold magenta]{asmetas_card.name}[/bold magenta]"
  )

  if ENVIRONMENT_AGENT_CARD_PATH.is_file():
    env_card = load_agent_card(ENVIRONMENT_AGENT_CARD_PATH)
    env_server_config = env_card.to_mcp_server_config()
  else:
    env_card = None
    env_cmd, *env_args = DEFAULT_ENVIRONMENT_COMMAND
    env_server_config = {
        "command": env_cmd,
        "args": env_args,
        "transport": "stdio",
    }

  asmetas_env = {
      "ASMETAS_URL": os.getenv("ASMETAS_URL", "http://localhost:8080")
  }
  mcp_config = {
      "environment_server": env_server_config,
      "asmetas_server": asmetas_card.to_mcp_server_config(env=asmetas_env),
  }

  client = MultiServerMCPClient(mcp_config)

  # Retrieve & Validate Tools
  try:
    asmetas_tools = await client.get_tools(server_name="asmetas_server")
    environment_tools = await client.get_tools(
        server_name="environment_server"
    )
  except Exception as e:
    print_error(f"Failed to connect to MCP servers: {e}")
    raise

  if missing := asmetas_card.validate_mcp_tools(asmetas_tools):
    raise RuntimeError(
        f"Missing required skills in AsmetaS contract: {missing}"
    )

  # Model Check & Enforcer Session Start
  sanitise_tool = next(
      (t for t in asmetas_tools if t.name == "sanitise_action"), None
  )
  start_tool = next(
      (t for t in asmetas_tools if t.name == "start_enforcer"), None
  )
  stop_tool = next(
      (t for t in asmetas_tools if t.name == "stop_enforcer"), None
  )

  if not sanitise_tool or not start_tool:
    raise RuntimeError("Essential Formal Gate tools missing from server.")

  await _verify_and_prepare_asmetas_model(asmetas_tools)

  init_res_raw = await start_tool.ainvoke({"asm_name": ASMETA_MODEL_NAME})
  init_data, _ = parse_mcp_response(init_res_raw)
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
        "asmetas_card": asmetas_card,
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

async def main():
  print_banner()

  model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
  print_info(f"Initializing LLM: [bold green]{model_name}[/bold green]")
  llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)

  try:
    async with setup_mcp_and_enforcer_session() as session:
      monitored_env = os.getenv("MONITORED_TOOLS")
      monitored_tools = (
          [t.strip() for t in monitored_env.split(",") if t.strip()]
          if monitored_env
          else None
      )

      graph = build_formal_gate_graph(
          llm=llm,
          environment_tools=session["environment_tools"],
          sanitise_action_tool=session["sanitise_tool"],
          policy=GATE_POLICY,
          error_policy=ERROR_POLICY,
          default_safe_action=DEFAULT_SAFE_ACTION,
          system_prompt=os.getenv("SYSTEM_PROMPT"),
          max_retries=MAX_RETRIES,
          agent_card=session["asmetas_card"],
          action_mapping=dict(ACTION_MAPPING),
          default_monitored_vars=dict(DEFAULT_MONITORED_VARIABLES),
          monitored_tools=monitored_tools,
      )

      print_ready_prompt()

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

  except Exception as err:
    print_error(f"Initialization or Session Error: {err}")
    sys.exit(1)
  finally:
    print_session_end()


if __name__ == "__main__":
  asyncio.run(main())