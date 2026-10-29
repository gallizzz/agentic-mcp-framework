"""Thin MCP facade. No ASM steps, medication rules, or commit logic here.

Started by the MCP server of a use case (e.g. use_cases/pillbox/mcp_server.py).
Only stdio is exposed in this example; the ASMETA HTTP service stays private.
"""

import asyncio

from enforcement.contracts import Plan
from enforcement.gateway import EnforcementGateway


def serve(gateway: EnforcementGateway) -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("Enforcement gateway")

    @server.tool()
    async def get_system_state() -> dict:
        """Read the current managed-system state and version without modifying it."""
        return await asyncio.to_thread(gateway.get_system_state)

    @server.tool()
    async def submit_plan(submission: Plan) -> dict:
        """Submit current action and residual plan. At most the first action is committed.

        Later actions must be resubmitted with a new request_id and current version.
        Only the server's ASM models authorize changes. No raw ASM inputs accepted.
        """
        return await asyncio.to_thread(gateway.submit_plan, submission)

    @server.tool()
    async def get_plan_status(request_id: str) -> dict:
        """Read the result of a submitted plan; does not execute it again."""
        return await asyncio.to_thread(gateway.get_plan_status, request_id)

    server.run(transport="stdio")
