"""MCP server of the pillbox use case (stdio).

Started by the agent as a child process (see config.py). It uploads the models listed in
enforcement.json, starts the ASM sessions and serves `submit_plan` / `get_system_state`.
If AsmetaS is unreachable it exits with code 1 and the chat does not start.
All use-case-specific logic is in the binding: this file only wires the pieces together.
"""

from pathlib import Path
import sys

# Makes `enforcement` and `use_cases` importable when run as a script (repository root)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enforcement.bootstrap import run_mcp_server
from use_cases.pillbox.binding import PillboxBinding

if __name__ == "__main__":
    raise SystemExit(run_mcp_server(PillboxBinding, Path(__file__).with_name("enforcement.json")))
