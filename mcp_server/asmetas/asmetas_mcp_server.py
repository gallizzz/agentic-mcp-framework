"""The AsmetaS MCP server for formal verification.

Provides a set of MCP tools for interacting with the AsmetaS formal verification engine.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any
import httpx
logging.getLogger("mcp").setLevel(logging.WARNING)
try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:
    from mcp.server.fastmcp import FastMCP as MCPServer

mcp = MCPServer("asmetas-formal-guard")

ASMETAS_URL = os.getenv("ASMETAS_URL", "http://localhost:8080").rstrip("/")

DEFAULT_MODEL_NAME = os.getenv("ASMETA_MODEL_NAME", "SafetyEnforcerModel.asm")
HTTP_TIMEOUT = 10.0
JSON_HEADERS = {"Content-Type": "application/json"}

current_execution_id: str | None = None
SESSION_FILE = Path(os.getenv("ASMETAS_SESSION_FILE", "/tmp/asmetas_session.json"))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _response(status: str, message: str, **extra: Any) -> str:
    """Serialises a uniform JSON tool response."""
    return json.dumps({"status": status, "message": message, **extra}, indent=2)

def _error(message: str) -> str:
    return _response("error", message)

def _parse_execution_id(response: httpx.Response) -> Any:
    """Extracts the execution ID from a /start response (JSON body or plain text)."""
    try:
        data = response.json()
        return data.get("id") or data.get("execution_id") or response.text.strip('" \n')
    except Exception:
        return response.text.strip('" \n')

def _is_valid_id(val: Any) -> bool:
    try:
        return int(val) > 0
    except (ValueError, TypeError):
        return False

def _load_execution_id() -> str | None:
    global current_execution_id
    if current_execution_id and _is_valid_id(current_execution_id):
        return current_execution_id
    if SESSION_FILE.is_file():
        try:
            with open(SESSION_FILE, "r") as f:
                candidate = str(json.load(f).get("execution_id", ""))
            if _is_valid_id(candidate):
                current_execution_id = candidate
                return current_execution_id
            SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    current_execution_id = None
    return None

def _save_execution_id(exec_id: str, model_name: str | None = None) -> None:
    global current_execution_id
    if not _is_valid_id(exec_id):
        _clear_execution_id()
        return
    current_execution_id = str(exec_id)
    try:
        with open(SESSION_FILE, "w") as f:
            json.dump({"execution_id": current_execution_id, "model_name": model_name}, f)
    except Exception as e:
        logging.warning(f"Could not save session file {SESSION_FILE}: {e}")

def _clear_execution_id() -> None:
    global current_execution_id
    current_execution_id = None
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except Exception:
        pass

async def _cleanup_all_running_models(client: httpx.AsyncClient) -> None:
    try:
        res = await client.get(f"{ASMETAS_URL}/running-models")
        if res.is_success:
            models_data = res.json().get("models", {})
            for m_id in list(models_data):
                try:
                    await client.delete(f"{ASMETAS_URL}/stop-model", params={"id": str(m_id)})
                except Exception:
                    pass
    except Exception as e:
        logging.warning(f"Failed to query or clean running models: {e}")

# ============================================================================
# MCP TOOLS DEFINITION
# ============================================================================

@mcp.tool()
async def list_models() -> str:
    """
    Retrieves the list of available ASM models and libraries loaded on the AsmetaS server.
    """
    url = f"{ASMETAS_URL}/model-list"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            return _error(f"Failed to list models: {str(e)}")


@mcp.tool()
async def delete_model(asm_name: str) -> str:
    """
    Deletes an ASM model from the AsmetaS server.
    """
    url = f"{ASMETAS_URL}/delete-model"
    params = {"name": asm_name}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            return _response("success", f"Model '{asm_name}' deleted successfully.")
        except httpx.HTTPError as e:
            return _error(f"Failed to delete model '{asm_name}': {str(e)}")


@mcp.tool()
async def start_enforcer(asm_name: str) -> str:
    """
    Starts the AsmetaS enforcer for the specified ASM model.
    """
    url = f"{ASMETAS_URL}/start"
    params = {"name": asm_name}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(url, params=params)
            response.raise_for_status()
            exec_id = _parse_execution_id(response)

            # Handle non-positive error IDs (e.g., -4: FullMapException)
            if not _is_valid_id(exec_id):
                logging.info(f"AsmetaS start returned non-positive ID ({exec_id}). Cleaning up stale models and retrying...")
                await _cleanup_all_running_models(client)
                response = await client.post(url, params=params)
                response.raise_for_status()
                exec_id = _parse_execution_id(response)

            if not _is_valid_id(exec_id):
                _clear_execution_id()
                return _error(f"AsmetaS server returned invalid execution ID: {exec_id}")

            _save_execution_id(str(exec_id), asm_name)
            return _response(
                "success",
                f"Enforcer started successfully for model '{asm_name}'",
                execution_id=str(exec_id),
            )
        except httpx.HTTPError as e:
            _clear_execution_id()
            return _error(f"Failed to start AsmetaS enforcer: {str(e)}")


@mcp.tool()
async def sanitise_action(monitored_variables: dict) -> str:
    """
    Evaluates and sanitises a proposed action against the formal ASM guard rules.
    """
    # _load_execution_id only ever returns valid (positive) IDs
    exec_id = _load_execution_id()
    if not exec_id:
        start_res = await start_enforcer(DEFAULT_MODEL_NAME)
        exec_id = _load_execution_id()
        if not exec_id:
            return _error(f"No active enforcer session found and start failed: {start_res}")

    url = f"{ASMETAS_URL}/step"

    # Convert all monitored variable values to strings for JSON serialization
    clean_monitored = {str(k): str(v) for k, v in monitored_variables.items()}
    input_action = clean_monitored.get("inputAction")
    payload = {"id": int(exec_id), "monitoredVariables": clean_monitored}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.put(url, json=payload, headers=JSON_HEADERS)
            # If server returns 500 or 404, session ID may be stale or crashed. Try restarting once.
            if response.status_code in (404, 500):
                logging.warning(f"AsmetaS step returned HTTP {response.status_code}. Resetting session and retrying...")
                _clear_execution_id()
                await start_enforcer(DEFAULT_MODEL_NAME)
                new_exec_id = _load_execution_id()
                if new_exec_id:
                    payload["id"] = int(new_exec_id)
                    response = await client.put(url, json=payload, headers=JSON_HEADERS)

            response.raise_for_status()

            # Extract the output action and compare with input action
            run_output = response.json().get("runOutput", {})
            out_values = run_output.get("outvalues", {})
            out_action = out_values.get("outAction")

            if not out_action:
                err_msg = run_output.get("message") or "AsmetaS step did not produce an outAction."
                return _error(f"AsmetaS enforcer step failed: {err_msg}")

            # Determine whether the action was approved or modified
            if out_action == input_action:
                verdict = "APPROVED"
                feedback = "Action satisfies formal safety properties."
                sanitised_action = input_action
            else:
                verdict = "VIOLATION"
                sanitised_action = out_action
                feedback = (
                    f"Proposed action '{input_action}' violates safety invariants. "
                    f"Action sanitised to '{sanitised_action}' by formal guard."
                )

            return json.dumps({
                "verdict": verdict,
                "input_action": input_action,
                "sanitised_action": sanitised_action,
                "feedback": feedback,
                "raw_output": out_values
            }, indent=2)

        except httpx.HTTPStatusError as e:
            _clear_execution_id()
            return _error(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.HTTPError as e:
            return _error(f"Failed to execute step in AsmetaS enforcer: {str(e)}")

@mcp.tool()
async def stop_enforcer() -> str:
    """
    Stops the active AsmetaS enforcer instance and clears local session state.
    """
    exec_id = _load_execution_id()
    if not exec_id:
        return _response("info", "No active enforcer session to stop.")

    url = f"{ASMETAS_URL}/stop-model"
    params = {"id": exec_id}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            _clear_execution_id()
            return _response("success", f"Enforcer session '{exec_id}' successfully stopped.")
        except httpx.HTTPError as e:
            # Clear local state anyway
            _clear_execution_id()
            return _response(
                "warning",
                f"Attempted to stop enforcer session '{exec_id}', HTTP warning: {str(e)}",
            )

if __name__ == "__main__":
    mcp.run()
