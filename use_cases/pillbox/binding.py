"""Pillbox data translation. Safety decisions and repairs are ONLY in ASM.

The trusted JSON (enforcement.json) holds the synthetic temporal parameters of the scenarios.
The LLM cannot provide clinical windows, minimum gaps, or preview verdicts.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from enforcement.contracts import (Action, AsmError, AsmState, Command, EnforcerOutput,
                           Plan, PreviewRequest, PreviewResult)


class DoseParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    compartment: Literal["compartment1", "compartment2"]
    dose_index: int = Field(ge=0)
    time: int = Field(ge=0, le=1439)  # The example interface represents one day.


class Deadline(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    compartment: Literal["compartment1", "compartment2"]
    dose_index: int = Field(ge=0)
    latest_time: int = Field(ge=0, le=1439)


class Goals(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    available_from: int = Field(default=0, ge=0, le=1439)
    latest_time: int = Field(default=1439, ge=0, le=1439)
    preview_deadline: Deadline | None = None


DEVICE_OUTPUTS = {
    "isPillMissed", "pillTakenWithDelay", "actual_time_consumption", "day",
    "time_consumption", "drugIndex", "name", "redLed", "pillboxSystemTime",
    "scheduleVersion", "lastAppliedCommandId", "lastRejectedCommandId",
}
COMMAND_OUTPUTS = {
    "setNewTime", "setOriginalTime", "newTime", "skipNextPill", "targetDoseIndex",
    "agentUpdate", "commandId", "commandBaseScheduleVersion",
}
PREVIEW_METADATA = (
    "previewRequestId", "previewBaseScheduleVersion", "previewTargetCompartment",
    "previewTargetDoseIndex", "previewCandidateTime",
)
PREVIEW_FEEDBACK = (
    "previewCompleted", "previewTimedOut", "previewResultRequestId",
    "previewResultBaseVersion", "previewOutcome",
)


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def select(values: dict[str, str], names: set[str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if key.split("(")[0] in names}


def dose_action(compartment: str, index: int, time: int) -> Action:
    return Action(kind="reschedule", parameters={
        "compartment": compartment, "dose_index": index, "time": time,
    })


class PillboxBinding:
    device_model = "pillboxDevice.asm"
    enforcer_model = "scheduler.asm"
    coordinator_model = "PreviewCoordinator.asm"
    setup_models = ("configurationMgr.asm",)

    def __init__(self, config_path: Path):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.compartments = self.config["compartments"]
        if self.compartments != ["compartment1", "compartment2"]:
            raise ValueError("The included ASM bundle defines exactly two compartments")

    def validate_plan(self, plan: Plan) -> None:
        # Representation checks, not checks of temporal safety or goal feasibility.
        for action in plan.actions:
            if action.kind != "reschedule":
                raise ValueError("This example supports only reschedule actions")
            parameters = DoseParameters.model_validate(action.parameters)
            if parameters.dose_index >= len(self.config["windows"][parameters.compartment]):
                raise ValueError("Dose index has no configured entry")
        goals = Goals.model_validate(plan.goals)
        if goals.preview_deadline is not None:
            deadline = goals.preview_deadline
            if deadline.dose_index >= len(self.config["windows"][deadline.compartment]):
                raise ValueError("Deadline refers to an unknown dose index")

    def initial_inputs(self) -> dict[str, str]:
        inputs = {"systemTime": str(self.config["system_time"]),
                  "openSwitch(1)": "false", "openSwitch(2)": "false"}
        for compartment in self.compartments:
            for name in ("setNewTime", "setOriginalTime", "skipNextPill", "agentUpdate"):
                inputs[f"{name}({compartment})"] = "false"
            for name in ("newTime", "targetDoseIndex", "commandId", "commandBaseScheduleVersion"):
                inputs[f"{name}({compartment})"] = "0"
            for other in self.compartments:
                inputs[f"skipNextPill({compartment},{other})"] = "false"
        return inputs

    def version(self, state: AsmState) -> int:
        return state.integer("scheduleVersion")

    def summary(self, state: AsmState) -> dict:
        schedule = {c: state.sequence(f"time_consumption({c})") for c in self.compartments}
        return {
            "version": self.version(state),
            "schedule": schedule,
            "schedule_hhmm": {c: [hhmm(t) for t in times] for c, times in schedule.items()},
            "last_applied_command": {c: state.integer(f"lastAppliedCommandId({c})") for c in self.compartments},
            "last_rejected_command": {c: state.integer(f"lastRejectedCommandId({c})") for c in self.compartments},
        }

    def enforcer_inputs(self, live: AsmState, plan: Plan | None = None,
                        command_id: int = 0,
                        preview: PreviewResult | None = None) -> dict[str, str]:
        inputs = select(live.outputs, DEVICE_OUTPUTS)
        inputs.update({
            "agentRequestPending": "false", "agentRequestId": "0",
            "agentTargetCompartment": "compartment1", "agentTargetDoseIndex": "0",
            "agentRequestedTime": "0", "patientAvailableFrom": "0", "agentGoalLatestTime": "1439",
            "agentExpectedScheduleVersion": str(self.version(live)),
            "clinicalEarliestTime": "0", "clinicalLatestTime": "1439",
            "previewCompleted": "false", "previewTimedOut": "false",
            "previewResultRequestId": "0", "previewResultBaseVersion": "0", "previewOutcome": "PREVIEW_NONE",
        })
        if plan is not None:
            action = DoseParameters.model_validate(plan.actions[0].parameters)
            goals = Goals.model_validate(plan.goals)
            earliest, latest = self.config["windows"][action.compartment][action.dose_index]
            inputs.update({
                "agentRequestPending": "true", "agentRequestId": str(command_id),
                "agentTargetCompartment": action.compartment, "agentTargetDoseIndex": str(action.dose_index),
                "agentRequestedTime": str(action.time), "patientAvailableFrom": str(goals.available_from),
                "agentGoalLatestTime": str(goals.latest_time),
                "agentExpectedScheduleVersion": str(plan.expected_version),
                "clinicalEarliestTime": str(earliest), "clinicalLatestTime": str(latest),
            })
        if preview is not None:
            inputs.update(preview.feedback)
        return inputs

    def enforcer_output(self, state: AsmState) -> EnforcerOutput:
        result = EnforcerOutput(state.integer("decisionRequestId"),
                                state.literal("agentDecision"), state.literal("agentReason"))
        if state.boolean("previewRequested"):
            candidate = dose_action(state.literal("previewTargetCompartment"),
                                    state.integer("previewTargetDoseIndex"), state.integer("previewCandidateTime"))
            result.preview_request = PreviewRequest(
                state.integer("previewRequestId"), state.integer("previewBaseScheduleVersion"),
                candidate, {name: state.literal(name) for name in PREVIEW_METADATA},
            )
        active = [c for c in self.compartments if state.boolean(f"setNewTime({c})")]
        if active:
            if len(active) != 1 or not state.boolean(f"agentUpdate({active[0]})"):
                raise AsmError("Reactive/multiple commands need a separate device-control integration")
            compartment = active[0]
            result.command = Command(
                state.integer(f"commandId({compartment})"),
                state.integer(f"commandBaseScheduleVersion({compartment})"),
                dose_action(compartment, state.integer(f"targetDoseIndex({compartment})"),
                            state.integer(f"newTime({compartment})")),
                select(state.outputs, COMMAND_OUTPUTS),
            )
        return result

    def command_inputs(self, live: AsmState, command: Command) -> dict[str, str]:
        inputs = self.initial_inputs()
        inputs["systemTime"] = live.literal("pillboxSystemTime")
        inputs.update(command.inputs)
        return inputs

    def action_inputs(self, current: AsmState, action: Action,
                      command_id: int) -> dict[str, str]:
        parameters = DoseParameters.model_validate(action.parameters)
        compartment = parameters.compartment
        inputs = self.initial_inputs()
        inputs["systemTime"] = current.literal("pillboxSystemTime")
        inputs.update({
            f"setNewTime({compartment})": "true", f"agentUpdate({compartment})": "true",
            f"targetDoseIndex({compartment})": str(parameters.dose_index),
            f"newTime({compartment})": str(parameters.time), f"commandId({compartment})": str(command_id),
            f"commandBaseScheduleVersion({compartment})": str(self.version(current)),
        })
        return inputs

    def same_target(self, left: Action, right: Action) -> bool:
        return (left.kind == right.kind and
                left.parameters["compartment"] == right.parameters["compartment"] and
                left.parameters["dose_index"] == right.parameters["dose_index"])

    def commit_applied(self, live: AsmState, command: Command) -> bool:
        parameters = DoseParameters.model_validate(command.action.parameters)
        compartment = parameters.compartment
        return (live.integer(f"lastAppliedCommandId({compartment})") == command.command_id and
                self.version(live) == command.base_version + 1 and
                live.sequence(f"time_consumption({compartment})")[parameters.dose_index] == parameters.time)

    def commit_rejected(self, live: AsmState, command: Command) -> bool:
        compartment = command.action.parameters["compartment"]
        return live.integer(f"lastRejectedCommandId({compartment})") == command.command_id

    def preview_inputs(self, current: AsmState, phase: str,
                       request: PreviewRequest, action: Action | None = None,
                       command_id: int = 0, goals: dict | None = None) -> dict[str, str]:
        inputs = {
            "previewBegin": "false", "previewInspect": "false", "previewFinalize": "false", "previewReset": "false",
            "previewExpectedCommandId": "0", "previewExpectedCompartment": "compartment1",
            "previewExpectedDoseIndex": "0", "previewExpectedTime": "0",
            "previewCheckGoal": "false", "previewGoalCompartment": "compartment1",
            "previewGoalDoseIndex": "0", "previewGoalLatestTime": "1439",
        }
        inputs.update(request.metadata)
        names = {"time_consumption": "previewTime_consumption", "drugIndex": "previewDrugIndex",
                 "scheduleVersion": "previewScheduleVersion", "lastAppliedCommandId": "previewLastAppliedCommandId",
                 "lastRejectedCommandId": "previewLastRejectedCommandId"}
        for key, value in current.outputs.items():
            name = key.split("(")[0]
            if name in names:
                inputs[names[name] + key[len(name):]] = value
        if phase == "begin":
            inputs["previewBegin"] = "true"
            for compartment, row in self.config["preview_min_gap"].items():
                for other, gap in row.items():
                    inputs[f"previewMinGap({compartment},{other})"] = str(gap)
        elif phase == "inspect":
            if action is None:
                raise ValueError("Inspection requires the action just executed")
            parameters = DoseParameters.model_validate(action.parameters)
            inputs.update({"previewInspect": "true", "previewExpectedCommandId": str(command_id),
                           "previewExpectedCompartment": parameters.compartment,
                           "previewExpectedDoseIndex": str(parameters.dose_index),
                           "previewExpectedTime": str(parameters.time)})
        elif phase == "finalize":
            inputs["previewFinalize"] = "true"
            deadline = Goals.model_validate(goals or {}).preview_deadline
            if deadline is not None:
                inputs.update({"previewCheckGoal": "true", "previewGoalCompartment": deadline.compartment,
                               "previewGoalDoseIndex": str(deadline.dose_index),
                               "previewGoalLatestTime": str(deadline.latest_time)})
        else:
            raise ValueError(f"Unknown preview phase: {phase}")
        return inputs

    def preview_output(self, state: AsmState) -> PreviewResult:
        if not state.boolean("previewCompleted") or state.boolean("previewTimedOut"):
            raise AsmError("No completed ASM preview result")
        outcome = state.literal("previewOutcome")
        if outcome not in ("PREVIEW_COMPATIBLE", "PREVIEW_CONFLICT", "PREVIEW_UNKNOWN"):
            raise AsmError("Invalid final preview outcome")
        return PreviewResult(outcome, state.integer("previewResultRequestId"),
                             state.integer("previewResultBaseVersion"),
                             {name: state.literal(name) for name in PREVIEW_FEEDBACK})
