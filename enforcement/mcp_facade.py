"""Thin MCP facade. No ASM steps, domain rules, or commit logic here.

Started by the MCP server of a use case (e.g. use_cases/pillbox/mcp_server.py).
Only stdio is exposed; the ASMETA HTTP service stays private.

Failures are returned as structured results, never as an invented ASM decision:
- "recovery_required": the gateway stopped after an operational error and
  refuses writes until the server is restarted;
- "invalid_request": the plan was rejected before reaching the ASM models.
"""

import asyncio
from typing import Any, Callable

from enforcement.contracts import AsmError, Plan
from enforcement.gateway import EnforcementGateway


def _guarded(call: Callable[..., dict], *args: Any) -> dict:
    try:
        return call(*args)
    except AsmError as exc:
        return {"status": "recovery_required", "decision": None, "reason": str(exc)}
    except ValueError as exc:
        return {"status": "invalid_request", "decision": None, "reason": str(exc)}


def serve(gateway: EnforcementGateway) -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("Enforcement gateway")
    read_only = ToolAnnotations(readOnlyHint=True)

    @server.tool(annotations=read_only)
    async def get_system_state() -> dict:
        """Read the current managed-system state and version without modifying it."""
        return await asyncio.to_thread(_guarded, gateway.get_system_state)

    @server.tool()
    async def submit_plan(submission: Plan) -> dict:
        """Submit current action and residual plan. At most the first action is committed.

        Later actions must be resubmitted with a new request_id and current version.
        Only the server's ASM models authorize changes. No raw ASM inputs accepted.
        """
        return await asyncio.to_thread(_guarded, gateway.submit_plan, submission)

    @server.tool(annotations=read_only)
    async def get_plan_status(request_id: str) -> dict:
        """Read the result of a submitted plan; does not execute it again."""
        return await asyncio.to_thread(gateway.get_plan_status, request_id)

    server.run(transport="stdio")
