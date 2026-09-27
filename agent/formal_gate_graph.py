"""
Complete LangGraph Formal Gate Graph implementation.
Coordinates Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action).
"""
import asyncio
import os
import time
from typing import Any, Callable, Dict, List, Literal, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.formal_gate_node import FormalGateNode
from agent.formal_gate_state import FormalAgentState

# Load environment
load_dotenv()
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

console = Console()


def create_planner_node(llm, tools: List[BaseTool], system_prompt: Optional[str] = None):
    """
    Creates the Planner LLM node with bound environment tools.
    """
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def planner_node(state: FormalAgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        # Prepend system prompt if provided and not already present
        if system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            messages = [SystemMessage(content=system_prompt)] + messages

        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return planner_node


def planner_router(state: FormalAgentState) -> str:
    """
    Inspects planner output. If a tool call was proposed, route to Formal Gate.
    Otherwise, conversation is complete -> route to END.
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "formal_gate"
    return END


def create_gate_router(policy: str, max_retries: int = 3):
    """
    Routes after Formal Gate evaluation.
    """
    def gate_router(state: FormalAgentState) -> str:
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
):
    """
    Builds and compiles the Formal Gate LangGraph:
    Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action).
    """
    # 1. Instantiate nodes
    planner = create_planner_node(llm, environment_tools, system_prompt)
    formal_gate = FormalGateNode(
        sanitise_action_callable=sanitise_action_tool,
        policy=policy,
        error_policy=error_policy,
    )
    environment = ToolNode(environment_tools) if environment_tools else None

    # 2. Build StateGraph
    builder = StateGraph(FormalAgentState)
    builder.add_node("planner", planner)
    builder.add_node("formal_gate", formal_gate)
    if environment:
        builder.add_node("environment", environment)

    # 3. Configure Edges
    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", planner_router)
    builder.add_conditional_edges("formal_gate", create_gate_router(policy, max_retries))

    if environment:
        # After tool execution, return to planner for final answer synthesis
        builder.add_edge("environment", "planner")

    return builder.compile()


def print_step_update(step_data: Dict[str, Any]):
    """
    Renders clean, styled terminal output for each node invocation.
    """
    timestamp = time.strftime('%X')

    if "planner" in step_data:
        msgs = step_data["planner"].get("messages", [])
        if msgs:
            msg = msgs[-1]
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    console.print(
                        f"[{timestamp}] 🤖 [Planner] Proposed action: '{tc['name']}' with args: {tc['args']}",
                        style="bold cyan"
                    )
            elif msg.content:
                console.print(f"\n[{timestamp}] 🤖 Agent:", style="bold cyan")
                console.print(Markdown(str(msg.content).strip()))

    if "formal_gate" in step_data:
        gate_res = step_data["formal_gate"]
        verdict = gate_res.get("guard_verdict")
        feedback = gate_res.get("guard_feedback")
        sanitised = gate_res.get("sanitised_action")

        if verdict == "APPROVED":
            console.print(
                f"[{timestamp}] 🛡️ [Formal Gate - AsmetaS] Verdict: [bold green]APPROVED[/bold green] | {feedback}",
                style="green"
            )
        elif verdict == "VIOLATION":
            sanitised_display = sanitised.get("args") if sanitised else "None"
            console.print(
                f"[{timestamp}] 🛡️ [Formal Gate - AsmetaS] Verdict: [bold yellow]VIOLATION[/bold yellow] | "
                f"Shielded/Sanitised to: {sanitised_display}\n"
                f"    [dim]Formal feedback: {feedback}[/dim]",
                style="yellow"
            )
        elif verdict == "ERROR":
            console.print(
                f"[{timestamp}] 🛡️ [Formal Gate - AsmetaS] Verdict: [bold red]ERROR[/bold red] | {feedback}",
                style="red"
            )
        elif verdict == "BYPASS":
            console.print(f"[{timestamp}] 🛡️ [Formal Gate] Bypass: {feedback}", style="dim")

    if "environment" in step_data:
        env_res = step_data["environment"].get("messages", [])
        for tool_msg in env_res:
            content = str(tool_msg.content).strip()
            max_len = 200
            truncated = content[:max_len] + ("..." if len(content) > max_len else "")
            console.print(f"[{timestamp}] ⚙️ [Environment Output] {truncated}", style="dim green")


async def main():
    """
    Interactive CLI runner for the Formal Gate Agent.
    """
    console.print(Panel.fit(
        "[bold cyan]LangGraph Formal Gate Architecture[/bold cyan]\n"
        "[dim]Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action)[/dim]",
        border_style="cyan"
    ))

    # LLM Initialization
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.8-flash",
        request_timeout=30.0,
        temperature=0.0,
    )

    # Initialize MCP Client
    console.print(f"[{time.strftime('%X')}] Initializing MCP servers...", style="dim")
    mcp_config = {
        "vehicle_server": {
            "command": "python",
            "args": ["mcp_server/vehicle_mcp_server.py"],
            "transport": "stdio",
        },
        "asmetas_server": {
            "command": "python",
            "args": ["mcp_server/asmetas/asmetas_mcp_server.py"],
            "transport": "stdio",
        },
    }

    client = MultiServerMCPClient(mcp_config)

    # Separate AsmetaS Formal Gate tools from Environment tools
    asmetas_tools = await client.get_tools(server_name="asmetas_server")
    vehicle_tools = await client.get_tools(server_name="vehicle_server")

    environment_tools = vehicle_tools
    console.print(f"[{time.strftime('%X')}] Environment tools: {[t.name for t in environment_tools]}", style="dim")
    console.print(f"[{time.strftime('%X')}] Formal Guard tools: {[t.name for t in asmetas_tools]}", style="dim")

    # Retrieve sanitise_action tool from AsmetaS
    sanitise_tool = next((t for t in asmetas_tools if t.name == "sanitise_action"), None)
    start_tool = next((t for t in asmetas_tools if t.name == "start_enforcer"), None)
    stop_tool = next((t for t in asmetas_tools if t.name == "stop_enforcer"), None)

    # Attempt to start AsmetaS formal enforcer session
    if start_tool:
        try:
            init_res = await start_tool.ainvoke({"asm_name": "SafetyEnforcerModel.asm"})
            console.print(f"[{time.strftime('%X')}] AsmetaS Enforcer status: {init_res}", style="dim")
        except Exception as e:
            console.print(f"[{time.strftime('%X')}] ⚠️ Warning: AsmetaS server not ready or unreachable ({e}). Gate will run in fail-safe fallback.", style="yellow")

    system_prompt = (
        "Sei un assistente intelligente che opera all'interno di un sistema critico di sicurezza per la guida autonoma. "
        "Hai a disposizione tool per interagire con l'ambiente del veicolo (execute_vehicle_action, get_vehicle_telemetry). "
        "Quando l'utente richiede un'azione di guida sul veicolo, usa execute_vehicle_action "
        "con l'azione opportuna (es. 'FASTER', 'SLOWER', 'KEEP', 'CHANGE_LANE'). "
        "Tutte le azioni sono sottoposte ad un Formal Gate deterministico basato su AsmetaS. "
        "Sii sintetico, chiaro e professionale."
    )

    # Build LangGraph graph
    graph = build_formal_gate_graph(
        llm=llm,
        environment_tools=environment_tools,
        sanitise_action_tool=sanitise_tool,
        policy="shielding",
        error_policy="fail_safe",
        system_prompt=system_prompt,
        max_retries=3,
    )

    console.print(f"\n[{time.strftime('%X')}] === Formal Gate Agent is ready! ===", style="bold green")
    console.print("Type your requests below. Type 'exit' or 'quit' to terminate.", style="dim")

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

                with console.status(f"[bold green][{time.strftime('%X')}] Formal Agent is executing...", spinner="dots"):
                    async for step_output in graph.astream(initial_state):
                        print_step_update(step_output)

                console.print("-" * 40, style="dim")
            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                console.print(f"[{time.strftime('%X')}] ❌ Errore durante l'esecuzione: {e}", style="bold red")
    finally:
        if stop_tool:
            try:
                await stop_tool.ainvoke({})
            except Exception:
                pass
        console.print(f"\n[{time.strftime('%X')}] Session terminated.", style="dim")


if __name__ == "__main__":
    asyncio.run(main())
