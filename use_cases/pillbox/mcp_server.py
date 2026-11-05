"""MCP server of the pillbox use case (stdio)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enforcement.bootstrap import run_mcp_server
from use_cases.pillbox.binding import PillboxBinding

if __name__ == "__main__":
    raise SystemExit(run_mcp_server(PillboxBinding, Path(__file__).with_name("enforcement.json")))
