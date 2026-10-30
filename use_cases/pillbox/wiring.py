"""Builds the enforcement gateway for the pillbox use case.

Shared by the scenario runner and the MCP server. Model locations and the list
of models to upload come from the "asmeta" section of enforcement.json.
"""

import json
from pathlib import Path

from enforcement.asm_runtime import ASMRuntimeAdapter
from enforcement.deploy import deploy
from enforcement.gateway import EnforcementGateway
from enforcement.rest_client import AsmetaRestClient
from use_cases.pillbox.binding import PillboxBinding

USE_CASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = USE_CASE_DIR / "enforcement.json"
DEFAULT_URL = "http://127.0.0.1:8080"


def _asmeta_section(config: Path) -> tuple[Path, list[Path], list[Path]]:
    """Models folder, model files and library files (paths relative to the config file)."""
    section = json.loads(config.read_text(encoding="utf-8"))["asmeta"]
    base = config.resolve().parent
    models_dir = (base / section["models_path"]).resolve()
    libraries_dir = (base / section["libraries_path"]).resolve()
    models = [models_dir / name for name in section["models"]]
    libraries = [libraries_dir / name for name in section["libraries"]]
    return models_dir, models, libraries


def deploy_models(client: AsmetaRestClient, config: Path = DEFAULT_CONFIG,
                  require_idle: bool = False) -> list[str]:
    """Uploads the configured models and libraries to the ASMETA service."""
    _, models, libraries = _asmeta_section(config)
    return deploy(client, models, libraries, require_idle=require_idle)


def build_gateway(client: AsmetaRestClient, config: Path = DEFAULT_CONFIG) -> EnforcementGateway:
    """Wires runtime, binding and gateway; call initialize() before use."""
    models_dir, _, _ = _asmeta_section(config)
    runtime = ASMRuntimeAdapter(client, models_dir)
    return EnforcementGateway(runtime, PillboxBinding(config))
