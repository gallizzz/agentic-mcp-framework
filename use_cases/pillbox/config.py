"""Pillbox use case: the enforcement gateway verifies and executes rescheduling plans.

`config.py` is what `core.config.load_use_case("pillbox")` imports (selected by USE_CASE in
.env). It must define `USE_CASE`. Files of a use case folder:
    config.py          this file: how the agent starts the server and instructs the planner
    planner_hints.md   domain instructions for the planner: vocabulary, units, how to report results
    mcp_server.py      entry point of the MCP server process (enforcement + binding)
    binding.py         domain <-> ASM translation (`ModelBinding`)
    enforcement.json   ASM files to upload (from resources/) and trusted domain parameters
    run_scenario.py    optional: runs JSON plans without the LLM
"""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent

# The agent runs the server command as a child process (stdio) and keeps it for the whole chat
USE_CASE = UseCaseConfig(
    mcp_server_command=[sys.executable, str(USE_CASE_DIR / "mcp_server.py")],
    max_steps_per_turn=6,  # enough to read the state and submit a few actions in one turn
    # Domain instructions appended to the planner system prompt (English)
    planner_hints=(USE_CASE_DIR / "planner_hints.md").read_text(encoding="utf-8"),
)
