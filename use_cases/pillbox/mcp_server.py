"""MCP server of the pillbox use case (stdio).

Uploads the configured models and initializes the enforcement gateway before
serving: if the ASMETA service is unreachable or a model cannot be loaded, the
process exits and the agent cannot start.
"""

import argparse
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from enforcement.mcp_facade import serve
from enforcement.rest_client import AsmetaRestClient
from use_cases.pillbox.wiring import DEFAULT_CONFIG, DEFAULT_URL, build_gateway, deploy_models


def main() -> int:
    parser = argparse.ArgumentParser(description="Pillbox enforcement MCP server (stdio)")
    parser.add_argument("--url", default=os.getenv("ASMETAS_URL", DEFAULT_URL))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    # stdout is the MCP channel: logs go to stderr only. The agent shares that stderr
    # with its chat, so only warnings and errors are shown here.
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s", stream=sys.stderr)

    client = AsmetaRestClient(args.url)
    gateway = None
    try:
        deploy_models(client, args.config)
        gateway = build_gateway(client, args.config)
        gateway.initialize()
        serve(gateway)
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        return 1
    finally:
        if gateway is not None:
            gateway.close()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
