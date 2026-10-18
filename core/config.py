"""Generic configuration of the Formal Gate engine and use-case loading.

Domain-specific settings (ASM model, environment MCP server, action mappings, policies)
live in `use_cases/<name>/config.py`, which must expose a `USE_CASE: UseCaseConfig`.
"""

from dataclasses import dataclass, field
import importlib
from pathlib import Path
import sys
from typing import Dict, List, Literal, Optional

CORE_DIR = Path(__file__).resolve().parent
USE_CASES_DIR = CORE_DIR.parent / "use_cases"

# AsmetaS MCP adapter (generic, shared by every use case)
ASMETAS_MCP_COMMAND = [sys.executable, str(CORE_DIR / "mcp_server" / "asmetas_mcp_server.py")]

# Maximum re-planning iterations (replan policy) before terminating the turn
MAX_RETRIES = 3

@dataclass(frozen=True)
class UseCaseConfig:
    """Everything the engine needs to know about a specific case study."""

    # Name of the ASM model registered on AsmetaS-web-service
    asm_model_name: str
    # Environment MCP server execution command (stdio)
    environment_mcp_command: List[str]
    # Safe fallback action when fail_safe is triggered. It bypasses the ASM, so it must be a value
    # accepted by both the environment tool and the ASM `inputAction` domain, and safe in every state.
    default_safe_action: str
    # Maps candidate environment actions to ASM model rule actions
    action_mapping: Dict[str, str] = field(default_factory=dict)
    # Default values for monitored sensor/probe variables if not provided
    default_monitored_variables: Dict[str, str] = field(default_factory=dict)
    # policy: "shielding" (force sanitised action) or "replan" (send feedback back to LLM)
    gate_policy: Literal["shielding", "replan"] = "shielding"
    # error_policy: "fail_safe" (execute default_safe_action on gate error) or "fail_stop" (abort turn)
    error_policy: Literal["fail_stop", "fail_safe"] = "fail_safe"

def available_use_cases() -> List[str]:
    """Names of the use cases found under use_cases/ (folders with a config.py)."""
    return sorted(p.parent.name for p in USE_CASES_DIR.glob("*/config.py"))

def load_use_case(name: Optional[str]) -> UseCaseConfig:
    """Imports `use_cases.<name>.config` and returns its USE_CASE definition."""
    available = ", ".join(available_use_cases()) or "none"
    if not name:
        raise RuntimeError(f"USE_CASE is not set in .env. Available use cases: {available}.")

    module_name = f"use_cases.{name}.config"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        # Only a missing use case is reported as such; broken imports inside it propagate
        if not module_name.startswith(e.name or "\0"):
            raise
        raise RuntimeError(
            f"Use case '{name}' not found (expected use_cases/{name}/config.py)."
            f" Available use cases: {available}."
        ) from e

    use_case = getattr(module, "USE_CASE", None)
    if not isinstance(use_case, UseCaseConfig):
        raise RuntimeError(f"use_cases/{name}/config.py must define USE_CASE = UseCaseConfig(...).")
    return use_case
