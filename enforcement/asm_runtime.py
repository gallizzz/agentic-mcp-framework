"""Session lifecycle and verified deterministic replay for isolated previews."""

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
from .contracts import AsmError, AsmService, AsmState
logger = logging.getLogger(__name__)

@dataclass
class Session:
    id: int
    model_name: str
    history: list[dict[str, str]] = field(default_factory=list)
    state: AsmState | None = None

@dataclass
class Snapshot:
    model_name: str
    history: list[dict[str, str]]
    state: AsmState
    sources_hash: str

class ASMRuntimeAdapter:
    def __init__(self, service: AsmService, models_folder: Path, max_replay_steps: int = 1000):
        self.service = service
        self.models_folder = models_folder
        self.max_replay_steps = max_replay_steps
        self.sources_hash = self._hash_sources()
        self.sessions: dict[int, Session] = {}

    def _hash_sources(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.models_folder.glob("*.asm")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def create(self, model_name: str) -> Session:
        if Path(model_name).name != model_name or not (self.models_folder / model_name).is_file():
            raise AsmError("Model is not in the trusted local bundle")
        if self._hash_sources() != self.sources_hash:
            raise AsmError("ASM sources changed after runtime initialization")
        session = Session(self.service.start(model_name), model_name)
        if session.id in self.sessions:
            raise AsmError("Runtime session aliasing")
        self.sessions[session.id] = session
        return session

    def _check_session(self, session: Session) -> None:
        if self.sessions.get(session.id) is not session:
            raise AsmError("Unknown or closed ASM session")

    def step(self, session: Session, inputs: dict[str, str]) -> AsmState:
        self._check_session(session)
        state = self.service.step(session.id, inputs)
        session.history.append(dict(inputs))
        session.state = deepcopy(state)
        return state

    def read(self, session: Session) -> AsmState:
        self._check_session(session)
        state = self.service.read(session.id)
        session.state = deepcopy(state)
        return state

    def snapshot(self, session: Session) -> Snapshot:
        return Snapshot(session.model_name, deepcopy(session.history),
                        deepcopy(self.read(session)), self.sources_hash)

    def replay(self, snapshot: Snapshot) -> Session:
        """Reproduce a recorded state, not an invented REST clone operation.

        This requires deterministic models and complete input history. The full
        materialized state is compared before any speculative action is executed.
        """
        if len(snapshot.history) > self.max_replay_steps:
            raise AsmError("Preview reconstruction exceeds the replay budget")
        if snapshot.sources_hash != self.sources_hash:
            raise AsmError("Preview and live model sources differ")
        preview = self.create(snapshot.model_name)
        try:
            for inputs in snapshot.history:
                self.step(preview, inputs)
            if self.read(preview).values() != snapshot.state.values():
                raise AsmError("Replay did not reconstruct the complete live state")
            return preview
        except Exception:
            self.stop(preview)
            raise

    def stop(self, session: Session) -> None:
        if session.id in self.sessions:
            self.service.stop(session.id)
            del self.sessions[session.id]

    def close(self) -> None:
        for session in list(self.sessions.values()):
            try:
                self.stop(session)
            except AsmError as exc:
                logger.error("Could not close ASM session %s: %s", session.id, exc)
