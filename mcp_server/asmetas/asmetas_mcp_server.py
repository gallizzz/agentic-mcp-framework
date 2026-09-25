import os
import json
import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("asmetas-formal-guard")

ASMETAS_URL = os.getenv("ASMETAS_URL", "http://localhost:8080").rstrip("/")

# Global execution state for the active enforcer instance
current_execution_id: str | None = None


@mcp.tool()
async def start_enforcer(asm_name: str) -> str:
    """
    Starts the AsmetaS enforcer for the specified ASM model.

    Args:
        asm_name: Name of the ASM model to start (e.g. 'SafetyEnforcerModel.asm')
    """
    global current_execution_id
    url = f"{ASMETAS_URL}/start"
    params = {"name": asm_name}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, params=params)
            response.raise_for_status()

            # Attempt to parse execution ID from JSON or text response
            try:
                data = response.json()
                exec_id = data.get("id") or data.get("execution_id") or response.text.strip('" \n')
            except Exception:
                exec_id = response.text.strip('" \n')

            current_execution_id = exec_id
            return json.dumps({
                "status": "success",
                "message": f"Enforcer started successfully for model '{asm_name}'",
                "execution_id": exec_id
            }, indent=2)
        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to start AsmetaS enforcer: {str(e)}"
            }, indent=2)


@mcp.tool()
async def sanitise_action(monitored_variables: dict) -> str:
    """
    Evaluates and sanitises a proposed action against the formal ASM guard rules.

    Args:
        monitored_variables: Dictionary containing inputAction and environment state variables.
                            Example: {"inputAction": "FASTER", "rightLaneFree": "false"}
    """
    global current_execution_id

    if not current_execution_id:
        return json.dumps({
            "status": "error",
            "message": "No active enforcer session found. Call start_enforcer first."
        }, indent=2)

    url = f"{ASMETAS_URL}/step"
    payload = {
        "id": current_execution_id,
        "monitoredVariables": monitored_variables
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.put(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract outAction from response structure
            run_output = data.get("runOutput", {})
            out_values = run_output.get("outvalues", {})
            out_action = out_values.get("outAction")

            input_action = monitored_variables.get("inputAction")

            if out_action == input_action:
                verdict = "APPROVED"
                feedback = "Action satisfies formal safety properties."
            else:
                verdict = "VIOLATION"
                feedback = (
                    f"Proposed action '{input_action}' violates safety invariants. "
                    f"Action sanitised to '{out_action}' by formal guard."
                )

            return json.dumps({
                "verdict": verdict,
                "input_action": input_action,
                "sanitised_action": out_action,
                "feedback": feedback,
                "raw_output": out_values
            }, indent=2)

        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to execute step in AsmetaS enforcer: {str(e)}"
            }, indent=2)


@mcp.tool()
async def stop_enforcer() -> str:
    """
    Stops the active AsmetaS enforcer instance and clears local session state.
    """
    global current_execution_id

    if not current_execution_id:
        return json.dumps({
            "status": "info",
            "message": "No active enforcer session to stop."
        }, indent=2)

    exec_id = current_execution_id
    url = f"{ASMETAS_URL}/stop-model"
    params = {"id": exec_id}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            current_execution_id = None
            return json.dumps({
                "status": "success",
                "message": f"Enforcer session '{exec_id}' successfully stopped."
            }, indent=2)
        except httpx.HTTPError as e:
            # Clear local state anyway
            current_execution_id = None
            return json.dumps({
                "status": "warning",
                "message": f"Attempted to stop enforcer session '{exec_id}', HTTP warning: {str(e)}"
            }, indent=2)


if __name__ == "__main__":
    mcp.run()
