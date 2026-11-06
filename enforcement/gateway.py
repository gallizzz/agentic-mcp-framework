"""Agent-facing application service: validation, orchestration and acknowledged commit.

`EnforcementGateway.submit_plan` is the heart of the framework. For every plan it runs this
pipeline, each step correlated by one `command_id`:

    1. validate the plan (pydantic schema + the binding's `validate_plan`);
    2. snapshot the live device and ask the ENFORCER ASM for a decision on the first action;
    3. if the enforcer asks for a preview, simulate the whole plan on a replayed twin and
       feed the verdict back to the enforcer;
    4. if the enforcer authorizes a command, re-check that the live state did not change,
       send the command to the live device and verify the ACK (applied or rejected);
    5. cross-check decision and ACK, and return the result to the MCP facade.

The gateway never decides anything about safety: it only moves data between ASM sessions
(through the use case's `ModelBinding`) and refuses to continue on any inconsistency.
"""

from copy import deepcopy
from dataclasses import asdict
import logging
from threading import RLock
from .asm_runtime import ASMRuntimeAdapter
from .contracts import DECISION_VERDICTS, AsmError, ModelBinding, Plan
from .preview_orchestrator import PreviewOrchestrator
logger = logging.getLogger(__name__)

class EnforcementGateway:
    """Owns the long-lived ASM sessions (live device, enforcer, setup models) and serializes
    every plan under one lock, so that two plans can never interleave on the live system."""

    def __init__(self, runtime: ASMRuntimeAdapter, binding: ModelBinding):
        self.runtime = runtime
        self.binding = binding
        self.preview = PreviewOrchestrator(runtime, binding)
        self.lock = RLock()
        self.live = None  # session of the live device model
        self.enforcer = None  # session of the enforcer model (takes every decision)
        self.setup_sessions = []  # optional models kept in sync after each applied command
        self.last_live = None  # last state read from the live device
        # Idempotency log: request_id -> {payload, status, result}. It also backs get_plan_status.
        self.records: dict[str, dict] = {}
        # Correlation id of the next request. It is sent to the ASM and must come back unchanged
        # in the enforcer output, in the command and in the ACK.
        self.next_command_id = 101
        # Set after any operational error: the gateway then refuses every further write
        # (fail-closed) until the MCP server is restarted.
        self.failed = False

    def initialize(self) -> None:
        """Starts the live device, the setup models and the enforcer with their first step.

        Called once at startup: if AsmetaS is unreachable or a model fails, the exception
        propagates and the MCP server exits, so the chat never starts (fail-fast).
        """
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
        """Guard for every operation: the gateway must be initialized and not in recovery."""
        if self.failed:
            raise AsmError("Gateway requires operator recovery; further writes are disabled")
        if self.live is None or self.enforcer is None:
            raise AsmError("Call initialize() first")

    def get_system_state(self) -> dict:
        """Read-only: rereads the live device and returns the binding's summary of it."""
        with self.lock:
            self._ready()
            self.last_live = self.runtime.read(self.live)
            return self.binding.summary(self.last_live)

    def get_plan_status(self, request_id: str) -> dict:
        """Read-only: result of an earlier submission, looked up by request_id."""
        with self.lock:
            record = self.records.get(request_id)
            if record is None:
                return {"request_id": request_id, "status": "not_found"}
            return deepcopy({"request_id": request_id,
                             "status": record["status"], "result": record["result"]})

    def submit_plan(self, submission: Plan | dict) -> dict:
        """Verifies and executes the FIRST action of the plan; returns a JSON-serializable result.

        Errors raised before the ASM models run (pydantic, `validate_plan`) propagate as
        ValueError: nothing changed and the facade reports `invalid_request`. Errors after
        that point are operational failures and put the gateway in recovery mode.
        The returned dict has `status` = `completed` (the ASM gave a decision, which may
        well be a refusal) or `recovery_required` (operational failure).
        """
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
                # STEP 1 - Ask the enforcer. The snapshot (state + input history of the live
                # device) is what the preview later replays and what every re-check compares to.
                snapshot = self.runtime.snapshot(self.live)
                self.last_live = snapshot.state
                inputs = self.binding.enforcer_inputs(snapshot.state, plan, command_id)
                state = self.runtime.step(self.enforcer, inputs)
                output = self.binding.enforcer_output(state)
                if output.request_id != command_id:
                    raise AsmError("Enforcer response belongs to another request")

                # STEP 2 - Preview (only if the enforcer asked for it). The whole plan is
                # simulated on a twin, never on the live system; the verdict goes back to the
                # enforcer, which then gives the final decision.
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

                # STEP 3 - Commit (only if the enforcer authorized a command). Before sending
                # it, every correlation is checked and the live state is verified unchanged:
                # the command must be exactly what the ASM evaluated, on the state it evaluated.
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
                    commit_started = True  # from here on a failure leaves the outcome "unknown"
                    # The live step is the only write to the real system. The ACK is read from
                    # the new live state, then mirrored to the enforcer (final decision).
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

                # STEP 4 - Final cross-checks: the decision must match what really happened
                # on the live system (ALLOW/REPLACE <=> command acknowledged as applied).
                if output.request_id != command_id:
                    raise AsmError("Final decision belongs to another request")
                if output.decision not in DECISION_VERDICTS:
                    raise AsmError("Enforcer has not returned a final decision")
                success = output.decision in ("ALLOW", "REPLACE")
                if success != commit_applied:
                    raise AsmError("Final decision and live execution acknowledgment disagree")
                if output.decision == "REPLACE" and preview_result is None:
                    raise AsmError("REPLACE without a computed preview")

                result = {
                    "request_id": plan.request_id, "status": "completed",
                    "decision": output.decision, "reason": output.reason,
                    **self._reason_explanation(output.reason),
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
                    "last_observed_state": self._observed_state(),
                    "preview": asdict(preview_result) if preview_result else None,
                }
                logger.error("Request %s requires recovery: %s", plan.request_id, exc)
            record["status"] = result["status"]
            record["result"] = deepcopy(result)
            return result

    def _reason_explanation(self, reason: str) -> dict:
        """`reason_explanation` field: the use case's plain-language meaning of the reason code."""
        explanation = self.binding.reason_glossary().get(reason)
        return {"reason_explanation": explanation} if explanation else {}

    def _observed_state(self) -> dict | None:
        """State for a failure report: reading it must never hide the failure itself."""
        try:
            return self.binding.summary(self.last_live)
        except Exception as exc:
            logger.error("Live state not readable for the failure report: %s", exc)
            return None

    def close(self) -> None:
        """Stops every ASM session opened by this gateway (called on regular server exit)."""
        with self.lock:
            self.runtime.close()
            self.live = None
            self.enforcer = None
            self.setup_sessions.clear()
