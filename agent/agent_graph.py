"""The graph-based orchestrator for LangGraph.

LangGraph execution pipeline coordinating Planner, Formal Gate, and Environment nodes."""

from contextlib import asynccontextmanager
import asyncio
import json
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
from agent.planner_node import create_planner_node, planner_router
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

async def _verify_asmetas_model(asmetas_tools: List[BaseTool]):
  """Verifies that the formal model is already available on the AsmetaS web service."""
  list_models_tool = next(
      (t for t in asmetas_tools if t.name == "list_models"), None
  )

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
  env_cmd, *env_args = ENVIRONMENT_MCP_COMMAND
  asmetas_cmd, *asmetas_args = ASMETAS_MCP_COMMAND

  asmetas_env = {
      "ASMETAS_URL": os.getenv("ASMETAS_URL", "http://localhost:8080")
  }
  mcp_config = {
      "environment_server": {
          "command": env_cmd,
          "args": env_args,
          "transport": "stdio",
      },
      "asmetas_server": {
          "command": asmetas_cmd,
          "args": asmetas_args,
          "transport": "stdio",
          "env": asmetas_env,
      },
  }

  client = MultiServerMCPClient(mcp_config)

  # Retrieve Tools from MCP Servers
  try:
    asmetas_tools = await client.get_tools(server_name="asmetas_server")
    environment_tools = await client.get_tools(
        server_name="environment_server"
    )
  except Exception as e:
    print_error(f"Failed to connect to MCP servers: {e}")
    raise

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
    raise RuntimeError(
        "Essential Formal Gate tools (sanitise_action, start_enforcer) missing from server."
    )

  await _verify_asmetas_model(asmetas_tools)

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