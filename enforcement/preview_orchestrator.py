"""Execute candidate + residual actions; the coordinator ASM decides the verdict."""

import logging

from .asm_runtime import ASMRuntimeAdapter, Snapshot
from .contracts import Action, AsmError, ModelBinding, PreviewRequest, PreviewResult

logger = logging.getLogger(__name__)


class PreviewOrchestrator:
    def __init__(self, runtime: ASMRuntimeAdapter, binding: ModelBinding):
        self.runtime = runtime
        self.binding = binding

    def run(self, snapshot: Snapshot, request: PreviewRequest,
            residual: list[Action], goals: dict) -> PreviewResult:
        if request.base_version != self.binding.version(snapshot.state):
            raise AsmError("Preview request does not match the live snapshot")
        twin = self.runtime.replay(snapshot)
        coordinator = None
        observations = []
        try:
            coordinator = self.runtime.create(self.binding.coordinator_model)
            current = self.runtime.read(twin)
            inputs = self.binding.preview_inputs(current, "begin", request)
            checked = self.runtime.step(coordinator, inputs)
            if not checked.boolean("previewCompleted"):
                actions = [request.candidate] + residual
                for index, action in enumerate(actions):
                    # IDs are local to this new isolated session. Avoid any ID
                    # already acknowledged in the reconstructed device state.
                    command_id = request.request_id + index
                    inputs = self.binding.action_inputs(current, action, command_id)
                    current = self.runtime.step(twin, inputs)
                    inputs = self.binding.preview_inputs(
                        current, "inspect", request, action, command_id,
                    )
                    checked = self.runtime.step(coordinator, inputs)
                    observations.append({
                        "action": action.model_dump(),
                        "command_id": command_id,
                        "state": self.binding.summary(current),
                        "checker_state": checked.values(),
                    })
                    logger.info("Preview inspected action %s", index + 1)
                inputs = self.binding.preview_inputs(current, "finalize", request, goals=goals)
                checked = self.runtime.step(coordinator, inputs)
            result = self.binding.preview_output(checked)
            if result.request_id != request.request_id or result.base_version != request.base_version:
                raise AsmError("Preview result belongs to another request or state version")
            result.observations = observations
            logger.info("ASM preview verdict: %s", result.outcome)
            return result
        finally:
            # Close only the sessions owned by this preview; never the live one.
            for session in (coordinator, twin):
                if session is not None:
                    self.runtime.stop(session)
