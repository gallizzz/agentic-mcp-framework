"""Generic entry points of an enforcement use case: MCP server and scenario runner.

A use case supplies its ModelBinding factory and its configuration file, whose
"asmeta" section lists the models and libraries to upload (paths relative to the file).

Typical use, in `use_cases/<name>/mcp_server.py`:

    raise SystemExit(run_mcp_server(MyBinding, Path(__file__).with_name("enforcement.json")))

The binding factory receives the path of the configuration file, so the binding can read
its own trusted parameters from the same JSON (any keys besides "asmeta" are the use case's).
"""

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sys
from typing import Callable

from dotenv import load_dotenv

from .asm_runtime import ASMRuntimeAdapter
from .contracts import ModelBinding
from .deploy import deploy
from .gateway import EnforcementGateway
from .mcp_facade import serve
from .rest_client import AsmetaRestClient

# Builds the use case's ModelBinding from the path of its configuration file
BindingFactory = Callable[[Path], ModelBinding]


def _asmeta_section(config: Path) -> tuple[Path, list[Path], list[Path]]:
    """Models folder, model files and library files of the configuration (paths resolved
    relative to the configuration file)."""
    section = json.loads(config.read_text(encoding="utf-8"))["asmeta"]
    base = config.resolve().parent
    models_dir = (base / section["models_path"]).resolve()
    libraries_dir = (base / section["libraries_path"]).resolve()
    models = [models_dir / name for name in section["models"]]
    libraries = [libraries_dir / name for name in section["libraries"]]
    return models_dir, models, libraries


def _deploy_models(client: AsmetaRestClient, config: Path,
                   require_idle: bool = False) -> list[str]:
    """Uploads the configured models and libraries to the ASMETA service."""
    _, models, libraries = _asmeta_section(config)
    return deploy(client, models, libraries, require_idle=require_idle)


@contextmanager
def _running_gateway(client: AsmetaRestClient, make_binding: BindingFactory,
                     config: Path) -> Iterator[EnforcementGateway]:
    """Uploads the models and yields an initialized gateway, closing it on exit.

    Any failure here (service offline, model not loadable) aborts startup: this is the
    blocking availability check required by the fail-fast rule."""
    _deploy_models(client, config)
    models_dir, _, _ = _asmeta_section(config)
    gateway = EnforcementGateway(ASMRuntimeAdapter(client, models_dir), make_binding(config))
    try:
        gateway.initialize()
        yield gateway
    finally:
        gateway.close()


def _base_parser(description: str, default_config: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", type=Path, default=default_config)
    return parser


def _client() -> AsmetaRestClient:
    """REST client for the URL in ASMETAS_URL (passed by the agent, see `_build_mcp_config`)."""
    url = os.getenv("ASMETAS_URL")
    if not url:
        raise RuntimeError("ASMETAS_URL is not set (see .env.example).")
    return AsmetaRestClient(url)


def run_mcp_server(make_binding: BindingFactory, default_config: Path) -> int:
    """Serves the gateway over MCP stdio.

    Models and gateway are ready before serving: if the ASMETA service is unreachable
    or a model cannot be loaded, the process exits and the agent cannot start.
    """
    args = _base_parser("Enforcement MCP server (stdio)", default_config).parse_args()
    # stdout is the MCP channel: logs go to stderr only. The agent shares that stderr
    # with its chat, so only warnings and errors are shown here.
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s", stream=sys.stderr)

    client = None
    try:
        client = _client()  # fails here if ASMETAS_URL is not set
        with _running_gateway(client, make_binding, args.config) as gateway:
            serve(gateway)
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        return 1
    finally:
        if client is not None:
            client.close()


def run_scenario_cli(make_binding: BindingFactory, default_config: Path) -> int:
    """Runs JSON plans without the LLM agent (controlled experiments)."""
    load_dotenv()  # no agent here to pass ASMETAS_URL on
    parser = _base_parser("Enforcement via the ASMETA REST service", default_config)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("deploy", help="Upload all configured models to an idle service")
    run = commands.add_parser("run", help="Execute one plan in a fresh simulated live session")
    run.add_argument("plan", type=Path, help="JSON plan")
    run.add_argument("--output", type=Path, help="Optional result JSON file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    client = None
    try:
        client = _client()  # fails here if ASMETAS_URL is not set
        if args.command == "deploy":
            uploaded = _deploy_models(client, args.config, require_idle=True)
            print(f"Models uploaded: {', '.join(uploaded)}. No active simulation was modified.")
            return 0
        with _running_gateway(client, make_binding, args.config) as gateway:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            result = gateway.submit_plan(plan)
        text = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if result["status"] == "completed" else 1
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        return 1
    finally:
        if client is not None:
            client.close()
