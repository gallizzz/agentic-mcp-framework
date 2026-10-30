"""Runs pillbox scenarios from JSON, without the LLM agent (controlled experiments).

    python use_cases/pillbox/run_scenario.py deploy
    python use_cases/pillbox/run_scenario.py run use_cases/pillbox/scenarios/compatible_repair.json
"""

import argparse
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enforcement.rest_client import AsmetaRestClient
from use_cases.pillbox.wiring import DEFAULT_CONFIG, DEFAULT_URL, build_gateway, deploy_models


def main() -> int:
    parser = argparse.ArgumentParser(description="Pillbox enforcement via the ASMETA REST service")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("deploy", help="Upload all configured models to an idle service")
    run = commands.add_parser("run", help="Execute one plan in a fresh simulated live session")
    run.add_argument("plan", type=Path, help="JSON plan, e.g. use_cases/pillbox/scenarios/compatible_repair.json")
    run.add_argument("--output", type=Path, help="Optional result JSON file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    client = AsmetaRestClient(args.url)
    gateway = None
    try:
        if args.command == "deploy":
            uploaded = deploy_models(client, args.config, require_idle=True)
            print(f"Models uploaded: {', '.join(uploaded)}. No active simulation was modified.")
            return 0
        deploy_models(client, args.config)
        gateway = build_gateway(client, args.config)
        gateway.initialize()
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
        if gateway is not None:
            gateway.close()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
