"""Agent-facing application service: validation, orchestration and acknowledged commit."""

from copy import deepcopy
from dataclasses import asdict
import logging
from threading import RLock

from .asm_runtime import ASMRuntimeAdapter
from .contracts import AsmError, ModelBinding, Plan
from .preview_orchestrator import PreviewOrchestrator

logger = logging.getLogger(__name__)


class EnforcementGateway:
    def __init__(self, runtime: ASMRuntimeAdapter, binding: ModelBinding):
        self.runtime = runtime
        self.binding = binding
        self.preview = PreviewOrchestrator(runtime, binding)
        self.lock = RLock()
        self.live = None
        self.enforcer = None
        self.setup_sessions = []
        self.last_live = None
        self.records: dict[str, dict] = {}
        self.next_command_id = 101
        self.failed = False

    def initialize(self) -> None:
        with self.lock:
            if self.failed:
                raise AsmError("Gateway requires operator recovery")
            if self.live is not None:
                return
            try:
                self.live = self.runtime.create(self.binding.device_model)
                self.last_live = self.runtime.step(self.live, self.binding.initial_inputs())
                for name in self.binding.setup_models:
                    session = self.runtime.create(name)
                    self.setup_sessions.append(session)
                    self.runtime.step(session, self.binding.enforcer_inputs(self.last_live))
                self.enforcer = self.runtime.create(self.binding.enforcer_model)
                self.runtime.step(self.enforcer, self.binding.enforcer_inputs(self.last_live))
            except Exception:
                self.failed = True
                self.runtime.close()
                raise

    def _ready(self) -> None:
        if self.failed:
            raise AsmError("Gateway requires operator recovery; further writes are disabled")
        if self.live is None or self.enforcer is None:
            raise AsmError("Call initialize() first")

    def get_system_state(self) -> dict:
        with self.lock:
            self._ready()
            self.last_live = self.runtime.read(self.live)
            return self.binding.summary(self.last_live)

    def get_plan_status(self, request_id: str) -> dict:
        with self.lock:
            record = self.records.get(request_id)
            if record is None:
                return {"request_id": request_id, "status": "not_found"}
            return deepcopy({"request_id": request_id,
                             "status": record["status"], "result": record["result"]})

    def submit_plan(self, submission: Plan | dict) -> dict:
        plan = Plan.model_validate(submission)
        self.binding.validate_plan(plan)
        payload = plan.model_dump(mode="json")
        with self.lock:
            # The same ID and payload return the existing result, never another commit.
            if plan.request_id in self.records:
                record = self.records[plan.request_id]
                if payload != record["payload"]:
                    raise ValueError("request_id was already used for a different plan")
                return deepcopy(record["result"])
            self._ready()
            record = {"payload": payload, "status": "evaluating", "result": None}
            self.records[plan.request_id] = record
            command_id = self.next_command_id
            self.next_command_id += 1
            preview_result = None
            commit_started = False
            commit_applied = False
            commit_rejected = False
            applied_action = None
            try:
                snapshot = self.runtime.snapshot(self.live)
                self.last_live = snapshot.state
                inputs = self.binding.enforcer_inputs(snapshot.state, plan, command_id)
                state = self.runtime.step(self.enforcer, inputs)
                output = self.binding.enforcer_output(state)
                if output.request_id != command_id:
                    raise AsmError("Enforcer response belongs to another request")

                preview_request = output.preview_request
                if preview_request is not None:
                    if preview_request.request_id != command_id:
                        raise AsmError("Wrong preview request correlation")
                    if not self.binding.same_target(preview_request.candidate, plan.actions[0]):
                        raise AsmError("The candidate changed the action target")
                    record["status"] = "previewing"
                    preview_result = self.preview.run(
                        snapshot, preview_request, plan.actions[1:], plan.goals,
                    )
                    self.last_live = self.runtime.read(self.live)
                    if self.last_live.values() != snapshot.state.values():
                        raise AsmError("Live state changed during preview; candidate not committed")
                    inputs = self.binding.enforcer_inputs(self.last_live, preview=preview_result)
                    state = self.runtime.step(self.enforcer, inputs)
                    output = self.binding.enforcer_output(state)

                command = output.command
                if command is not None:
                    if command.command_id != command_id:
                        raise AsmError("Wrong command correlation")
                    if command.base_version != self.binding.version(snapshot.state):
                        raise AsmError("Command was evaluated against another state version")
                    expected = plan.actions[0]
                    if preview_result is not None:
                        if preview_result.outcome != "PREVIEW_COMPATIBLE":
                            raise AsmError("Enforcer emitted a command after a non-compatible preview")
                        expected = preview_request.candidate
                    if command.action != expected:
                        raise AsmError("Command differs from the action evaluated by the ASM models")
                    self.last_live = self.runtime.read(self.live)
                    if self.last_live.values() != snapshot.state.values():
                        raise AsmError("Live state changed before dispatch; command not sent")

                    record["status"] = "committing"
                    inputs = self.binding.command_inputs(self.last_live, command)
                    commit_started = True
                    self.last_live = self.runtime.step(self.live, inputs)
                    commit_applied = self.binding.commit_applied(self.last_live, command)
                    commit_rejected = self.binding.commit_rejected(self.last_live, command)
                    state = self.runtime.step(self.enforcer, self.binding.enforcer_inputs(self.last_live))
                    output = self.binding.enforcer_output(state)
                    if commit_applied:
                        applied_action = command.action.model_dump()
                        for session in self.setup_sessions:
                            self.runtime.step(session, self.binding.enforcer_inputs(self.last_live))
                    elif not commit_rejected:
                        raise AsmError("No matching live execution acknowledgment")

                if output.request_id != command_id:
                    raise AsmError("Final decision belongs to another request")
                if output.decision not in ("ALLOW", "REPLACE", "REPLAN", "BLOCK"):
                    raise AsmError("Enforcer has not returned a final decision")
                success = output.decision in ("ALLOW", "REPLACE")
                if success != commit_applied:
                    raise AsmError("Final decision and live execution acknowledgment disagree")
                if output.decision == "REPLACE" and preview_result is None:
                    raise AsmError("REPLACE without a computed preview")

                result = {
                    "request_id": plan.request_id, "status": "completed",
                    "decision": output.decision, "reason": output.reason,
                    "applied_action": applied_action,
                    "acknowledged_command_id": command_id if commit_applied else None,
                    "committed_actions": 1 if commit_applied else 0,
                    "commit_outcome": "applied" if commit_applied else "not_applied",
                    "remaining_actions": len(plan.actions) - (1 if commit_applied else 0),
                    "system_state": self.binding.summary(self.last_live),
                    "preview": asdict(preview_result) if preview_result else None,
                }
            except Exception as exc:
                # This is an operational failure, NOT an ASM BLOCK/REPLAN verdict.
                # A timeout after dispatch does not prove that the write was cancelled.
                self.failed = True
                outcome = "not_applied"
                if commit_applied:
                    outcome = "applied"
                elif commit_started and not commit_rejected:
                    outcome = "unknown"
                result = {
                    "request_id": plan.request_id, "status": "recovery_required",
                    "decision": None, "reason": str(exc), "commit_outcome": outcome,
                    "applied_action": applied_action,
                    "last_observed_state": self.binding.summary(self.last_live),
                    "preview": asdict(preview_result) if preview_result else None,
                }
                logger.error("Request %s requires recovery: %s", plan.request_id, exc)
            record["status"] = result["status"]
            record["result"] = deepcopy(result)
            return result

    def close(self) -> None:
        with self.lock:
            self.runtime.close()
            self.live = None
            self.enforcer = None
            self.setup_sessions.clear()
