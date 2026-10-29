"""Small data objects and the two interfaces used by the reusable modules."""

from dataclasses import dataclass, field
import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AsmError(RuntimeError):
    """The service or the execution protocol did not provide valid evidence."""


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str
    parameters: dict[str, Any]


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=0)
    actions: list[Action] = Field(min_length=1, max_length=32)
    goals: dict[str, Any] = Field(default_factory=dict)


@dataclass
class AsmState:
    outputs: dict[str, str]
    controlled: dict[str, str]

    def values(self) -> dict[str, str]:
        return {**self.controlled, **self.outputs}

    def literal(self, name: str) -> str:
        values = self.values()
        if name not in values:
            raise AsmError(f"Missing ASM value: {name}")
        return values[name]

    def integer(self, name: str) -> int:
        value = self.literal(name).strip()
        if not re.fullmatch(r"[0-9]+n?", value):
            raise AsmError(f"Expected Natural for {name}, got {value!r}")
        return int(value.removesuffix("n"))

    def boolean(self, name: str) -> bool:
        value = self.literal(name)
        if value not in ("true", "false"):
            raise AsmError(f"Expected Boolean for {name}, got {value!r}")
        return value == "true"

    def sequence(self, name: str) -> list[int]:
        value = self.literal(name)
        if not re.fullmatch(r"\[\s*(?:\d+n?\s*(?:,\s*\d+n?\s*)*)?\]", value):
            raise AsmError(f"Expected Seq(Natural) for {name}, got {value!r}")
        return json.loads(re.sub(r"(\d)n\b", r"\1", value))


@dataclass
class Command:
    command_id: int
    base_version: int
    action: Action
    inputs: dict[str, str]


@dataclass
class PreviewRequest:
    request_id: int
    base_version: int
    candidate: Action
    metadata: dict[str, str]


@dataclass
class PreviewResult:
    outcome: str
    request_id: int
    base_version: int
    feedback: dict[str, str]
    observations: list[dict] = field(default_factory=list)


@dataclass
class EnforcerOutput:
    request_id: int
    decision: str
    reason: str
    command: Command | None = None
    preview_request: PreviewRequest | None = None


class AsmService(Protocol):
    """Operations required of a runtime. The supplied client uses REST only."""

    def start(self, model_name: str) -> int: ...
    def step(self, session_id: int, inputs: dict[str, str]) -> AsmState: ...
    def read(self, session_id: int) -> AsmState: ...
    def stop(self, session_id: int) -> None: ...


class ModelBinding(Protocol):
    """Translate application data to/from ASM I/O, without deciding safety.

    A different domain supplies a different implementation of this interface.
    No model name, medication, interval, or compartment belongs to the core.
    """

    device_model: str
    enforcer_model: str
    coordinator_model: str
    setup_models: tuple[str, ...]

    def validate_plan(self, plan: Plan) -> None: ...
    def initial_inputs(self) -> dict[str, str]: ...
    def version(self, state: AsmState) -> int: ...
    def summary(self, state: AsmState) -> dict: ...

    def enforcer_inputs(self, live: AsmState, plan: Plan | None = None,
                        command_id: int = 0,
                        preview: PreviewResult | None = None) -> dict[str, str]: ...
    def enforcer_output(self, state: AsmState) -> EnforcerOutput: ...
    def command_inputs(self, live: AsmState, command: Command) -> dict[str, str]: ...
    def action_inputs(self, current: AsmState, action: Action,
                      command_id: int) -> dict[str, str]: ...
    def same_target(self, left: Action, right: Action) -> bool: ...
    def commit_applied(self, live: AsmState, command: Command) -> bool: ...
    def commit_rejected(self, live: AsmState, command: Command) -> bool: ...

    def preview_inputs(self, current: AsmState, phase: str,
                       request: PreviewRequest, action: Action | None = None,
                       command_id: int = 0,
                       goals: dict | None = None) -> dict[str, str]: ...
    def preview_output(self, state: AsmState) -> PreviewResult: ...
