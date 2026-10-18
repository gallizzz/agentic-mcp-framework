"""CLI Formatter and Terminal UI Renderer for the Formal Gate Agent.

Handles Rich styling, step rendering, text extraction, and status banners.
"""

import time
from typing import Any, Dict
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

ENV_OUTPUT_MAX_LEN = 200

def _log(message: str, style: str) -> None:
    console.print(f"[{time.strftime('%X')}] {message}", style=style)

def extract_text_content(content: Any) -> str:
    """
    Extracts clean plain text from strings, list of content blocks, or dictionaries.
    """
    if isinstance(content, list):
        return "\n".join(extract_text_content(part) for part in content).strip()
    if isinstance(content, dict) and "text" in content:
        content = content["text"]
    return str(content).strip()

# ============================================================================
# STATUS MESSAGES
# ============================================================================

def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]LangGraph Formal Gate[/bold cyan]\n"
            "[dim]Planner (LLM) -> Formal Gate (AsmetaS) -> Environment[/dim]",
            border_style="cyan",
        )
    )

def print_info(message: str):
    _log(message, "dim")

def print_error(message: str):
    _log(message, "bold red")

def print_success(message: str):
    _log(message, "green")

def print_ready_prompt():
    console.print()
    _log("Formal Gate Agent ready.", "bold green")
    console.print("Type your requests below. Type 'exit' or 'quit' to terminate.", style="dim")

def print_divider():
    console.print("-" * 40, style="dim")

def print_session_end():
    console.print()
    _log("Session terminated.", "dim")

def get_status_spinner(message: str = "Processing..."):
    return console.status(f"[bold green][{time.strftime('%X')}] {message}", spinner="dots")

# ============================================================================
# GRAPH STEP RENDERING
# ============================================================================

_VERDICT_STYLES = {"APPROVED": "green", "VIOLATION": "yellow", "ERROR": "red"}

def _render_planner(update: Dict[str, Any]) -> None:
    msgs = update.get("messages", [])
    if not msgs:
        return
    msg = msgs[-1]
    for tc in getattr(msg, "tool_calls", None) or []:
        _log(f"Proposed action: '{tc['name']}' ({tc['args']})", "bold cyan")
    if not getattr(msg, "tool_calls", None):
        text = extract_text_content(msg.content)
        if text:
            console.print()
            console.print(Markdown(text))

def _render_formal_gate(update: Dict[str, Any]) -> None:
    verdict = update.get("guard_verdict")
    feedback = update.get("guard_feedback")

    if verdict == "BYPASS":
        _log(f"Bypass: {feedback}", "dim")
    elif verdict in _VERDICT_STYLES:
        style = _VERDICT_STYLES[verdict]
        message = f"Verdict: [bold {style}]{verdict}[/bold {style}] | "
        if verdict == "VIOLATION":
            sanitised = update.get("sanitised_action")
            message += (
                f"Shielded to: {sanitised.get('args') if sanitised else 'None'}\n"
                f"    [dim]Feedback: {feedback}[/dim]"
            )
        else:
            message += str(feedback)
        _log(message, style)

def _render_environment(update: Dict[str, Any]) -> None:
    for tool_msg in update.get("messages", []):
        content = extract_text_content(tool_msg.content)
        if len(content) > ENV_OUTPUT_MAX_LEN:
            content = content[:ENV_OUTPUT_MAX_LEN] + "..."
        _log(content, "dim green")

_STEP_RENDERERS = {
    "planner": _render_planner,
    "formal_gate": _render_formal_gate,
    "environment": _render_environment,
}

def print_step_update(step_data: Dict[str, Any]):
    for node_name, render in _STEP_RENDERERS.items():
        if node_name in step_data:
            render(step_data[node_name])
