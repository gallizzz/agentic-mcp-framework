"""Runs pillbox scenarios from JSON, without the LLM agent (controlled experiments).

    python use_cases/pillbox/run_scenario.py deploy   # upload the models to an idle service
    python use_cases/pillbox/run_scenario.py run use_cases/pillbox/scenarios/M1.json

`run` executes the JSON plan in a fresh simulated session through the same gateway used by
the agent, so the ASM verdict can be tested without the LLM. Optional file for a use case.
"""

from pathlib import Path
import sys

# Makes `enforcement` and `use_cases` importable when run as a script (repository root)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enforcement.bootstrap import run_scenario_cli
from use_cases.pillbox.binding import PillboxBinding

if __name__ == "__main__":
    raise SystemExit(run_scenario_cli(PillboxBinding, Path(__file__).with_name("enforcement.json")))
