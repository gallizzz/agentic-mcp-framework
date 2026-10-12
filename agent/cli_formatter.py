"""CLI Formatter and Terminal UI Renderer for the Formal Gate Agent.

Handles Rich styling, step rendering, text extraction, and status banners.
"""

import time
from typing import Any, Dict
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

def extract_text_content(content: Any) -> str:
    """
    Extracts clean plain text from strings, list of content blocks, or dictionaries.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(str(part["text"]))
            elif isinstance(part, str):
                text_parts.append(part)
            else:
                text_parts.append(str(part))
        return "\n".join(text_parts).strip()
    if isinstance(content, dict) and "text" in content:
        return str(content["text"]).strip()
    return str(content).strip()

def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]LangGraph Formal Gate[/bold cyan]\n"
            "[dim]Planner (LLM) -> Formal Gate (AsmetaS) -> Environment[/dim]",
            border_style="cyan",
        )
    )

def print_info(message: str, prefix_time: bool = True):
    ts = f"[{time.strftime('%X')}] " if prefix_time else ""
    console.print(f"{ts}{message}", style="dim")

def print_warning(message: str, prefix_time: bool = True):
    ts = f"[{time.strftime('%X')}] " if prefix_time else ""
    console.print(f"{ts}{message}", style="yellow")

def print_error(message: str, prefix_time: bool = True):
    ts = f"[{time.strftime('%X')}] " if prefix_time else ""
    console.print(f"{ts}{message}", style="bold red")

def print_success(message: str, prefix_time: bool = True):
    ts = f"[{time.strftime('%X')}] " if prefix_time else ""
    console.print(f"{ts}{message}", style="green")

def print_ready_prompt():
    console.print(
        f"\n[{time.strftime('%X')}] Formal Gate Agent ready.",
        style="bold green",
    )
    console.print("Type your requests below. Type 'exit' or 'quit' to terminate.", style="dim")

def print_divider():
    console.print("-" * 40, style="dim")

def print_session_end():
    console.print(f"\n[{time.strftime('%X')}] Session terminated.", style="dim")

def get_status_spinner(message: str = "Processing..."):
    return console.status(
        f"[bold green][{time.strftime('%X')}] {message}",
        spinner="dots",
    )

def print_step_update(step_data: Dict[str, Any]):
    timestamp = time.strftime("%X")

    if "planner" in step_data:
        msgs = step_data["planner"].get("messages", [])
        if msgs:
            msg = msgs[-1]
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    console.print(
                        f"[{timestamp}] [planner] Proposed action: '{tc['name']}' ({tc['args']})",
                        style="bold cyan",
                    )
            elif msg.content:
                text = extract_text_content(msg.content)
                if text:
                    console.print(f"\n[{timestamp}] [agent]", style="bold cyan")
                    console.print(Markdown(text))

    if "formal_gate" in step_data:
        gate_res = step_data["formal_gate"]
        verdict = gate_res.get("guard_verdict")
        feedback = gate_res.get("guard_feedback")
        sanitised = gate_res.get("sanitised_action")

        if verdict == "APPROVED":
            console.print(
                f"[{timestamp}] [formal-gate] Verdict: [bold green]APPROVED[/bold green] | {feedback}",
                style="green",
            )
        elif verdict == "VIOLATION":
            sanitised_display = sanitised.get("args") if sanitised else "None"
            console.print(
                f"[{timestamp}] [formal-gate] Verdict: [bold yellow]VIOLATION[/bold yellow] | "
                f"Shielded to: {sanitised_display}\n"
                f"    [dim]Feedback: {feedback}[/dim]",
                style="yellow",
            )
        elif verdict == "ERROR":
            console.print(
                f"[{timestamp}] [formal-gate] Verdict: [bold red]ERROR[/bold red] | {feedback}",
                style="red",
            )
        elif verdict == "BYPASS":
            console.print(f"[{timestamp}] [formal-gate] Bypass: {feedback}", style="dim")

    if "environment" in step_data:
        env_res = step_data["environment"].get("messages", [])
        for tool_msg in env_res:
            content = extract_text_content(tool_msg.content)
            max_len = 200
            truncated = content[:max_len] + ("..." if len(content) > max_len else "")
            console.print(f"[{timestamp}] [env] {truncated}", style="dim green")
