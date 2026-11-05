"""Thin MCP facade. No ASM steps, domain rules, or commit logic here.

Started by enforcement/bootstrap.py in the MCP server of a use case.
Only stdio is exposed; the ASMETA HTTP service stays private.
"""

import asyncio
from typing import Any, Callable

from enforcement.contracts import STATE_TOOL, SUBMIT_TOOL, AsmError, Plan
from enforcement.gateway import EnforcementGateway


SUBMIT_DESCRIPTION = (
    "Modify the system by submitting the current action and any later actions of the plan. "
    "Only the server's ASM models authorize changes; raw ASM inputs are not accepted.\n"
    "`submission` contains ONLY these fields, with no others:\n"
    "- `request_id`: any string, it is replaced automatically;\n"
    "- `expected_version`: the `version` you have just read with `get_system_state`;\n"
    "- `actions`: the ordered list of actions;\n"
    "- `goals` (optional): the constraints the user gave for the first action.\n"
    "At most the FIRST action is applied, possibly corrected by the enforcer; the others only serve to "
    "verify the plan. For later actions, reread the state and send a new `submit_plan` with the new "
    "version, the list of remaining actions and, in `goals`, only the constraints the user gave for that "
    "action (if they gave none, omit `goals`)."
)


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

    mcp = FastMCP("Enforcement gateway")
    read_only = ToolAnnotations(readOnlyHint=True)

    @mcp.tool(name=STATE_TOOL, annotations=read_only)
    async def get_system_state() -> dict:
        """Read the current managed-system state and version without modifying it."""
        return await asyncio.to_thread(_guarded, gateway.get_system_state)

    description = SUBMIT_DESCRIPTION + "\n" + gateway.binding.plan_description().strip()

    # The parameter name must match contracts.SUBMIT_ARGUMENT
    @mcp.tool(name=SUBMIT_TOOL, description=description)
    async def submit_plan(submission: Plan) -> dict:
        return await asyncio.to_thread(_guarded, gateway.submit_plan, submission)

    @mcp.tool(annotations=read_only)
    async def get_plan_status(request_id: str) -> dict:
        """Read the result of a submitted plan; does not execute it again."""
        return await asyncio.to_thread(gateway.get_plan_status, request_id)

    mcp.run(transport="stdio")
