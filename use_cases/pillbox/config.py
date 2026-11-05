"""Pillbox use case: the enforcement gateway verifies and executes rescheduling plans."""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent

PLANNER_HINTS = """\
- The system is a pillbox with several compartments (synthetic data). `get_system_state` returns `medication`, which says which medication each compartment holds.
- The user only knows medication names and knows nothing about compartments and indexes. You translate the medication into the compartment using `medication`, and "first dose" / "second dose" into the index (the first is index 0). In your answers always talk about medications, doses and times in HH:MM format: never mention compartment names, indexes or times in minutes.
- In the tools, times are minutes from midnight (0-1439): for example 17:30 = 1050, 19:00 = 1140. Dose indexes start at 0.
- Never convert minutes to times yourself: to tell the user the current times, copy them from `schedule_hhmm`, which you find in `get_system_state` and in the `system_state` of the `submit_plan` result.
"""

USE_CASE = UseCaseConfig(
    mcp_server_command=[sys.executable, str(USE_CASE_DIR / "mcp_server.py")],
    max_steps_per_turn=6,
    planner_hints=PLANNER_HINTS,
)
