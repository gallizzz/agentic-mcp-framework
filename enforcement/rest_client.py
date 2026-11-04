"""HTTP client for the original FOSELAB AsmetaServer.jar.

No AsmetaComp, Java bridge, generated scripts, or automatic write retries.
"""

import logging
from pathlib import Path
import httpx
from .contracts import AsmError, AsmState
logger = logging.getLogger(__name__)

class AsmetaRestClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.http = httpx.Client(base_url=base_url, timeout=timeout,
                                 trust_env=False, follow_redirects=False)
        self.sessions: dict[int, str] = {}
        self.failed = False

    def _request(self, method: str, path: str, *, parse_json: bool = True, **kwargs) -> dict:
        # A timeout may follow a step already applied by the server.
        # Never retry a write or silently continue using uncertain sessions.
        if self.failed and path != "/stop-model":
            raise AsmError("REST client requires operator recovery after an earlier error")
        try:
            response = self.http.request(method, path, **kwargs)
            response.raise_for_status()
            if not parse_json:
                return {}  # /upload-model returns text, not the step JSON contract.
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            self.failed = True
            raise AsmError(f"{method} {path} failed; not retried: {exc}") from exc

    def running_models(self) -> dict:
        models = self._request("GET", "/running-models").get("models")
        if not isinstance(models, dict):
            raise AsmError("Invalid running-models response")
        return models

    def inventory(self) -> set[str]:
        """Names of the files stored in the service's models folder."""
        models = self._request("GET", "/model-list").get("models")
        if not isinstance(models, list):
            raise AsmError("Invalid model inventory")
        return set(models)

    def upload(self, path: Path) -> None:
        """Administrative upload to the models folder; a same-name file is replaced."""
        with path.open("rb") as stream:
            self._request("POST", "/upload-model",
                          files={"file": (path.name, stream, "text/plain")}, parse_json=False)

    def start(self, model_name: str) -> int:
        if Path(model_name).name != model_name or not model_name.endswith(".asm"):
            raise ValueError("Use a trusted deployed model name, not a client filesystem path")
        data = self._request("POST", "/start", params={"name": model_name})
        session_id = data.get("id")
        if type(session_id) is not int or session_id <= 0:
            raise AsmError(f"Cannot start {model_name}: {data}")
        if session_id in self.sessions:
            self.failed = True
            raise AsmError("The service reused an active session ID")
        self.sessions[session_id] = model_name
        return session_id

    def _state(self, data: dict, session_id: int) -> AsmState:
        if session_id not in self.sessions:
            raise AsmError("Unknown or closed session")
        if type(data.get("id")) is not int or data["id"] != session_id:
            raise AsmError("Wrong session ID in response")
        if "modelName" in data and data["modelName"] != self.sessions[session_id]:
            raise AsmError("Response belongs to another model")
        output = data.get("runOutput")
        if not isinstance(output, dict):
            raise AsmError("Missing runOutput")
        if output.get("esit") != "SAFE" or output.get("timeoutFlag") is not False:
            raise AsmError(f"ASM step failed or is inconclusive: {output.get('message')}")
        for name in ("outvalues", "controlledvalues"):
            values = output.get(name)
            if not isinstance(values, dict):
                raise AsmError(f"Missing {name}")
            for key, value in values.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise AsmError(f"Invalid ASM literal in {name}")
        outputs = output["outvalues"]
        controlled = output["controlledvalues"]
        for name in outputs.keys() & controlled.keys():
            if outputs[name] != controlled[name]:
                raise AsmError(f"Inconsistent state for {name}")
        return AsmState(outputs, controlled)

    def step(self, session_id: int, inputs: dict[str, str]) -> AsmState:
        if session_id not in self.sessions:
            raise AsmError("Unknown or closed session")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in inputs.items()):
            raise ValueError("Monitored inputs must be ASM literals encoded as strings")
        data = self._request("PUT", "/step", json={
            "id": session_id, "monitoredVariables": inputs,
        })
        try:
            return self._state(data, session_id)
        except AsmError:
            self.failed = True
            raise

    def read(self, session_id: int) -> AsmState:
        data = self._request("GET", "/get-model-status", params={"id": session_id})
        return self._state(data, session_id)

    def stop(self, session_id: int) -> None:
        if session_id not in self.sessions:
            return
        data = self._request("DELETE", "/stop-model", params={"id": session_id})
        if data.get("status") is not True:
            raise AsmError(f"Could not stop session {session_id}: {data}")
        del self.sessions[session_id]

    def close(self) -> None:
        for session_id in list(self.sessions):
            try:
                self.stop(session_id)
            except AsmError as exc:
                logger.error("Session cleanup failed: %s", exc)
        self.http.close()
