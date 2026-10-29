"""Builds the enforcement gateway for the pillbox use case.

Shared by the scenario runner and the MCP server: the only place that
knows where the pillbox ASM models and the trusted configuration live.
"""

from pathlib import Path

from enforcement.asm_runtime import ASMRuntimeAdapter
from enforcement.gateway import EnforcementGateway
from enforcement.rest_client import AsmetaRestClient
from use_cases.pillbox.binding import PillboxBinding

USE_CASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = USE_CASE_DIR.parents[1]
MODELS_DIR = REPO_ROOT / "resources" / "models"
LIBRARIES_DIR = REPO_ROOT / "resources" / "libraries"
DEFAULT_CONFIG = USE_CASE_DIR / "enforcement.json"
DEFAULT_URL = "http://127.0.0.1:8080"


def asm_sources() -> list[Path]:
    """Model and library files to upload to the ASMETA service."""
    return sorted(MODELS_DIR.glob("*.asm")) + sorted(LIBRARIES_DIR.glob("*.asm"))


def build_gateway(client: AsmetaRestClient, config: Path = DEFAULT_CONFIG) -> EnforcementGateway:
    """Wires runtime, binding and gateway; call initialize() before use."""
    runtime = ASMRuntimeAdapter(client, MODELS_DIR)
    return EnforcementGateway(runtime, PillboxBinding(config))
