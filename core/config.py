"""Generic configuration of the Formal Gate engine and use-case loading.

Domain-specific settings (MCP server, ASM models, planner instructions) live in
`use_cases/<name>/`, whose `config.py` must expose a `USE_CASE: UseCaseConfig`.
"""

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import List, Optional

USE_CASES_DIR = Path(__file__).resolve().parent.parent / "use_cases"

@dataclass(frozen=True)
class UseCaseConfig:
    """Everything the engine needs to know about a specific case study.

    The use-case MCP server verifies every action with its ASM models through the
    enforcement framework, executes it and returns the decision to the Formal Gate.
    """
    environment_mcp_command: List[str]
    max_steps_per_turn: int = 3
    planner_hints: str = ""

    def __post_init__(self):
        if self.max_steps_per_turn < 1:
            raise ValueError("max_steps_per_turn must be at least 1.")

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
