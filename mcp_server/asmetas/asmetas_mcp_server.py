import logging
import os
import json
from pathlib import Path
from typing import Any
import httpx

# Suppress internal MCP server request info logs
logging.getLogger("mcp").setLevel(logging.WARNING)

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:
    from mcp.server.fastmcp import FastMCP as MCPServer

mcp = MCPServer("asmetas-formal-guard")

ASMETAS_URL = os.getenv("ASMETAS_URL", "http://localhost:8080").rstrip("/")

# Global execution state for the active enforcer instance with file persistence
current_execution_id: str | None = None
SESSION_FILE = Path(os.getenv("ASMETAS_SESSION_FILE", "/tmp/asmetas_session.json"))


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
                data = json.load(f)
                candidate = str(data.get("execution_id", ""))
                if _is_valid_id(candidate):
                    current_execution_id = candidate
                    return current_execution_id
                else:
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
    if SESSION_FILE.is_file():
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass


async def _cleanup_all_running_models(client: httpx.AsyncClient) -> None:
    try:
        res = await client.get(f"{ASMETAS_URL}/running-models")
        if res.is_success:
            models_data = res.json().get("models", {})
            for m_id in list(models_data.keys()):
                try:
                    await client.delete(f"{ASMETAS_URL}/stop-model", params={"id": str(m_id)})
                except Exception:
                    pass
    except Exception as e:
        logging.warning(f"Failed to query or clean running models: {e}")


@mcp.tool()
async def list_models() -> str:
    """
    Retrieves the list of available ASM models and libraries loaded on the AsmetaS server.
    """
    url = f"{ASMETAS_URL}/model-list"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to list models: {str(e)}"
            }, indent=2)


@mcp.tool()
async def upload_model(model_path: str) -> str:
    """
    Uploads an ASM model file to the AsmetaS runtime server.
    Also ensures the StandardLibrary.asm is present on the server if needed.

    Args:
        model_path: Path to the .asm model file to upload.
    """
    path = Path(model_path).resolve()
    if not path.is_file():
        return json.dumps({
            "status": "error",
            "message": f"Model file not found at: {model_path}"
        }, indent=2)

    model_name = path.name
    url = f"{ASMETAS_URL}/upload-model"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            with open(path, "rb") as f:
                files = {"file": (model_name, f.read(), "application/octet-stream")}
                response = await client.post(url, files=files)
                response.raise_for_status()

            # Check if StandardLibrary is uploaded
            stdl_name = "StandardLibrary.asm"
            library_uploaded = False
            try:
                list_res = await client.get(f"{ASMETAS_URL}/model-list")
                if list_res.is_success:
                    data = list_res.json()
                    libraries = data.get("libraries", [])
                    if stdl_name not in libraries:
                        stdl_candidates = [
                            path.parent.parent / "libraries" / stdl_name,
                            path.parent / stdl_name,
                            Path(__file__).resolve().parent.parent.parent.parent / "AsmetaS-web-service" / "resources" / "libraries" / stdl_name,
                        ]
                        for candidate in stdl_candidates:
                            if candidate.is_file():
                                with open(candidate, "rb") as lf:
                                    lib_files = {"file": (stdl_name, lf.read(), "application/octet-stream")}
                                    await client.post(f"{ASMETAS_URL}/upload-library", files=lib_files)
                                    library_uploaded = True
                                    break
            except Exception as e:
                logging.warning(f"Could not verify or auto-upload standard library: {e}")

            return json.dumps({
                "status": "success",
                "message": f"Model '{model_name}' successfully uploaded to AsmetaS.",
                "model_name": model_name,
                "standard_library_uploaded": library_uploaded
            }, indent=2)
        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to upload model '{model_name}': {str(e)}"
            }, indent=2)


@mcp.tool()
async def upload_library(library_path: str) -> str:
    """
    Uploads an ASM library file (e.g. StandardLibrary.asm) to the AsmetaS runtime server.

    Args:
        library_path: Path to the .asm library file to upload.
    """
    path = Path(library_path).resolve()
    if not path.is_file():
        return json.dumps({
            "status": "error",
            "message": f"Library file not found at: {library_path}"
        }, indent=2)

    lib_name = path.name
    url = f"{ASMETAS_URL}/upload-library"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            with open(path, "rb") as f:
                files = {"file": (lib_name, f.read(), "application/octet-stream")}
                response = await client.post(url, files=files)
                response.raise_for_status()

            return json.dumps({
                "status": "success",
                "message": f"Library '{lib_name}' successfully uploaded to AsmetaS.",
                "library_name": lib_name
            }, indent=2)
        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to upload library '{lib_name}': {str(e)}"
            }, indent=2)


@mcp.tool()
async def delete_model(asm_name: str) -> str:
    """
    Deletes an ASM model from the AsmetaS server.

    Args:
        asm_name: Name of the ASM model to delete (e.g. 'SafetyEnforcerModel.asm').
    """
    url = f"{ASMETAS_URL}/delete-model"
    params = {"name": asm_name}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            return json.dumps({
                "status": "success",
                "message": f"Model '{asm_name}' deleted successfully."
            }, indent=2)
        except httpx.HTTPError as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to delete model '{asm_name}': {str(e)}"
            }, indent=2)


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

            # Handle non-positive error IDs (e.g., -4: FullMapException)
            if not _is_valid_id(exec_id):
                logging.info(f"AsmetaS start returned non-positive ID ({exec_id}). Cleaning up stale models and retrying...")
                await _cleanup_all_running_models(client)
                retry_response = await client.post(url, params=params)
                retry_response.raise_for_status()
                try:
                    retry_data = retry_response.json()
                    exec_id = retry_data.get("id") or retry_data.get("execution_id") or retry_response.text.strip('" \n')
                except Exception:
                    exec_id = retry_response.text.strip('" \n')

            if not _is_valid_id(exec_id):
                _clear_execution_id()
                return json.dumps({
                    "status": "error",
                    "message": f"AsmetaS server returned invalid execution ID: {exec_id}"
                }, indent=2)

            _save_execution_id(str(exec_id), asm_name)
            return json.dumps({
                "status": "success",
                "message": f"Enforcer started successfully for model '{asm_name}'",
                "execution_id": str(exec_id)
            }, indent=2)
        except httpx.HTTPError as e:
            _clear_execution_id()
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
    exec_id = _load_execution_id()
    default_model = os.getenv("ASMETA_MODEL_NAME", "SafetyEnforcerModel.asm")
    if not exec_id or not _is_valid_id(exec_id):
        start_res = await start_enforcer(default_model)
        exec_id = _load_execution_id()
        if not exec_id or not _is_valid_id(exec_id):
            return json.dumps({
                "status": "error",
                "message": f"No active enforcer session found and start failed: {start_res}"
            }, indent=2)

    url = f"{ASMETAS_URL}/step"

    # Convert all monitored variable values to strings for JSON serialization
    clean_monitored = {str(k): str(v) for k, v in monitored_variables.items()}
    input_action = clean_monitored.get("inputAction")

    # Prepare payload with execution ID and monitored variables
    payload = {
        "id": int(exec_id),
        "monitoredVariables": clean_monitored
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.put(
                url, 
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            # If server returns 500 or 404, session ID may be stale or crashed. Try restarting once.
            if response.status_code in (404, 500):
                logging.warning(f"AsmetaS step returned HTTP {response.status_code}. Resetting session and retrying...")
                _clear_execution_id()
                await start_enforcer(default_model)
                new_exec_id = _load_execution_id()
                if new_exec_id and _is_valid_id(new_exec_id):
                    payload["id"] = int(new_exec_id)
                    response = await client.put(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )

            response.raise_for_status()
            data = response.json()

            # Extract the output action and compare with input action
            run_output = data.get("runOutput", {})
            out_values = run_output.get("outvalues", {})
            out_action = out_values.get("outAction")

            if not out_action:
                err_msg = run_output.get("message") or "AsmetaS step did not produce an outAction."
                return json.dumps({
                    "status": "error",
                    "message": f"AsmetaS enforcer step failed: {err_msg}"
                }, indent=2)

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
            return json.dumps({
                "status": "error",
                "message": f"HTTP {e.response.status_code}: {e.response.text}"
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
    exec_id = _load_execution_id()
    if not exec_id:
        return json.dumps({
            "status": "info",
            "message": "No active enforcer session to stop."
        }, indent=2)

    url = f"{ASMETAS_URL}/stop-model"
    params = {"id": exec_id}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            _clear_execution_id()
            return json.dumps({
                "status": "success",
                "message": f"Enforcer session '{exec_id}' successfully stopped."
            }, indent=2)
        except httpx.HTTPError as e:
            # Clear local state anyway
            _clear_execution_id()
            return json.dumps({
                "status": "warning",
                "message": f"Attempted to stop enforcer session '{exec_id}', HTTP warning: {str(e)}"
            }, indent=2)


if __name__ == "__main__":
    mcp.run()
