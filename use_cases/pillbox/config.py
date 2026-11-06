"""Pillbox use case: the enforcement gateway verifies and executes rescheduling plans.

`config.py` is what `core.config.load_use_case("pillbox")` imports (selected by USE_CASE in
.env). It must define `USE_CASE`. Files of a use case folder:
    config.py          this file: how the agent starts the server and instructs the planner
    mcp_server.py      entry point of the MCP server process (enforcement + binding)
    binding.py         domain <-> ASM translation (`ModelBinding`)
    enforcement.json   ASM files to upload (from resources/) and trusted domain parameters
    run_scenario.py    optional: runs JSON plans without the LLM
"""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent

# Domain instructions appended to the planner system prompt (English). Use them for what the
# generic prompt cannot know: the user's vocabulary, unit conversions, how to report results.
PLANNER_HINTS = """\
- The system is a pillbox with several compartments (synthetic data). `get_system_state` returns `medication`, which says which medication each compartment holds.
- The user only knows medication names and knows nothing about compartments and indexes. You translate the medication into the compartment using `medication`, and "first dose" / "second dose" into the index (the first is index 0). In your answers always talk about medications, doses and times in HH:MM format: never mention compartment names, indexes or times in minutes.
- In the tools, times are minutes from midnight (0-1439): for example 17:30 = 1050, 19:00 = 1140. Dose indexes start at 0.
- Never convert minutes to times yourself: to tell the user the current times, copy them from `schedule_hhmm`, which you find in `get_system_state` and in the `system_state` of the `submit_plan` result.
"""

# The agent runs the server command as a child process (stdio) and keeps it for the whole chat
USE_CASE = UseCaseConfig(
    mcp_server_command=[sys.executable, str(USE_CASE_DIR / "mcp_server.py")],
    max_steps_per_turn=6,  # enough to read the state and submit a few actions in one turn
    planner_hints=PLANNER_HINTS,
)
