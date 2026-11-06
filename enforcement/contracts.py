"""Shared contracts of the enforcement framework: data objects and the two interfaces.

This is the file to read first when writing a new use case. It defines:

* the constants shared with the agent's Formal Gate (tool names, decision -> verdict map);
* the data objects exchanged between the gateway, the preview orchestrator and the binding
  (`Plan`, `Action`, `Command`, `PreviewRequest`, `PreviewResult`, `EnforcerOutput`, `AsmState`);
* `AsmService`, the runtime interface (implemented by the REST client);
* `ModelBinding`, the interface a use case implements to connect a domain to the ASM models.

Nothing here knows any domain: names of actions, models and parameters belong to the use case.
"""

from dataclasses import dataclass, field
import json
import re
from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# CONTRACT WITH THE AGENT'S FORMAL GATE (core/ imports only this file)
# ============================================================================

# Names of the MCP tools exposed by every use-case server (see mcp_facade.py)
SUBMIT_TOOL = "submit_plan"  # the ONLY tool that modifies the system
SUBMIT_ARGUMENT = "submission"  # name of the Plan parameter of SUBMIT_TOOL
STATE_TOOL = "get_system_state"  # read-only; also used as the startup health check
# Final decisions of the enforcer (the ASM) -> verdicts shown by the Formal Gate:
#   ALLOW   the action was executed as requested
#   REPLACE the ASM corrected the action; the corrected one was executed
#   REPLAN  nothing was executed; the planner can propose something else
#   BLOCK   nothing was executed; the turn ends with an explanation
DECISION_VERDICTS = {
    "ALLOW": "APPROVED",
    "REPLACE": "SHIELDED",
    "REPLAN": "REPLAN",
    "BLOCK": "BLOCKED",
}

class AsmError(RuntimeError):
    """The service or the execution protocol did not provide valid evidence.

    It is an OPERATIONAL failure (unreachable service, inconsistent answer, broken
    correlation), never a safety verdict: the gateway turns it into `recovery_required`.
    """

# ============================================================================
# PLAN: what the LLM submits (validated by pydantic before reaching any ASM)
# ============================================================================

class Action(BaseModel):
    """One domain action. `kind` and `parameters` are interpreted only by the use-case binding."""
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str
    parameters: dict[str, Any]

class Plan(BaseModel):
    """The ordered list of actions the LLM wants to execute, plus optional constraints.

    `request_id` is assigned by the Formal Gate (never by the LLM). `expected_version` is
    the state version the LLM read: a mismatch with the live system is rejected by the ASM.
    `goals` is a free-form dict whose meaning is defined by the use case (`plan_description`).
    """
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=0)
    actions: list[Action] = Field(min_length=1, max_length=32)
    goals: dict[str, Any] = Field(default_factory=dict)

# ============================================================================
# ASM STATE AND PROTOCOL OBJECTS
# ============================================================================

@dataclass
class AsmState:
    """State of one ASM session after a step, as returned by AsmetaS.

    `outputs` are the model's out-functions, `controlled` its controlled functions. Values
    are always strings in ASM syntax; the typed accessors below validate and convert them.
    Function arguments are part of the key, e.g. `"time_consumption(compartment1)"`.
    """
    outputs: dict[str, str]
    controlled: dict[str, str]

    def values(self) -> dict[str, str]:
        """Complete materialized state (used to compare two states for equality)."""
        return {**self.controlled, **self.outputs}

    def literal(self, name: str) -> str:
        """Raw ASM value; fails if the model does not expose `name`."""
        values = self.values()
        if name not in values:
            raise AsmError(f"Missing ASM value: {name}")
        return values[name]

    def integer(self, name: str) -> int:
        """Natural number (ASM prints it with an optional `n` suffix, e.g. `10n`)."""
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
        """Sequence of naturals, e.g. `[600n, 720n]` -> `[600, 720]`."""
        value = self.literal(name)
        if not re.fullmatch(r"\[\s*(?:\d+n?\s*(?:,\s*\d+n?\s*)*)?\]", value):
            raise AsmError(f"Expected Seq(Natural) for {name}, got {value!r}")
        return json.loads(re.sub(r"(\d)n\b", r"\1", value))

@dataclass
class Command:
    """What the enforcer authorizes to send to the live system.

    `command_id` correlates request, preview, command and ACK; `base_version` is the state
    version the ASM evaluated; `inputs` are the raw ASM outputs the binding turns into live inputs.
    """
    command_id: int
    base_version: int
    action: Action
    inputs: dict[str, str]

@dataclass
class PreviewRequest:
    """The enforcer asks to simulate `candidate` (+ the rest of the plan) before committing it.

    `metadata` is echoed back to the ASM in every preview step, to correlate the answer.
    """
    request_id: int
    base_version: int
    candidate: Action
    metadata: dict[str, str]

@dataclass
class PreviewResult:
    """Verdict of the coordinator ASM on a simulated plan (outcome strings are domain-defined,
    the gateway only requires `PREVIEW_COMPATIBLE` before any command is committed).

    `feedback` is fed back to the enforcer; `observations` is the per-step evidence.
    """
    outcome: str
    request_id: int
    base_version: int
    feedback: dict[str, str]
    observations: list[dict] = field(default_factory=list)

@dataclass
class EnforcerOutput:
    """Decoded output of one enforcer step.

    Typical sequence: the first step may carry a `preview_request`; after the preview the
    second step carries the `command` (only if the preview was compatible) or a final
    decision without command. The request_id must always equal the gateway's command_id."""
    request_id: int
    decision: str  # final when it is a key of DECISION_VERDICTS (the gateway rejects anything else at the end)
    reason: str  # reason code, explained by ModelBinding.reason_glossary()
    command: Command | None = None
    preview_request: PreviewRequest | None = None

# ============================================================================
# INTERFACES
# ============================================================================

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

    HOW A NEW USE CASE USES IT
    The gateway (gateway.py) drives four kinds of ASM sessions, whose model files you name
    in the class attributes below:

    * device     the simulated live system (what the agent really modifies);
    * enforcer   the ASM that takes every decision (ALLOW/REPLACE/REPLAN/BLOCK);
    * coordinator the ASM that judges a simulated plan during a preview;
    * setup      optional ASMs kept in sync with the live system after each commit.

    For each of them the binding builds the monitored INPUTS of the next step from the
    plan or the live state, and decodes the OUTPUTS into the objects of this file.
    The binding only translates and checks representation: every safety decision stays
    in the ASM models. Methods are grouped below in the order the gateway calls them.
    """

    # --- Model files (names of files listed in the `asmeta` section of the config) ---
    device_model: str
    enforcer_model: str
    coordinator_model: str
    setup_models: tuple[str, ...]

    # --- LLM-facing descriptions and plan validation ---
    def validate_plan(self, plan: Plan) -> None:
        """Representation checks on the plan (known action kinds, parameter types and ranges).
        Raise ValueError to reject it BEFORE any ASM runs: the planner is told to fix it.
        Never check safety or feasibility here, that is the ASM's job."""
        ...
    def plan_description(self) -> str:
        """LLM-facing text appended to the submit tool description: the action kinds
        with their parameters and the meaning of `goals`. Plan fields common to every
        domain are described by the facade."""
        ...
    def reason_glossary(self) -> dict[str, str]:
        """LLM-facing meaning of each reason code the enforcer can return. The gateway
        attaches the entry of the returned reason to the result; the text may also say
        what to do next."""
        ...

    # --- Live system: initialization and observation ---
    def initial_inputs(self) -> dict[str, str]:
        """Monitored inputs of the first device step (also the 'idle' baseline for later steps)."""
        ...
    def version(self, state: AsmState) -> int:
        """Version counter of the live state, increased by every applied change. It lets the
        enforcer reject plans built on stale readings (`Plan.expected_version`)."""
        ...
    def summary(self, state: AsmState) -> dict:
        """JSON-serializable state shown to the LLM by `get_system_state`. It MUST contain
        `version` (see `version()`); put here whatever the planner needs to build plans."""
        ...

    # --- Enforcer: request in, decision out ---
    def enforcer_inputs(self, live: AsmState, plan: Plan | None = None,
                        command_id: int = 0,
                        preview: PreviewResult | None = None) -> dict[str, str]:
        """Inputs of one enforcer step. Called in three ways: with `plan` (new request, the
        enforcer sees the live state and the FIRST action), with `preview` (the preview
        verdict, to get the final decision), with neither (idle step that only mirrors the
        live state, e.g. to acknowledge a commit). `command_id` is the request correlation id."""
        ...
    def enforcer_output(self, state: AsmState) -> EnforcerOutput:
        """Decode the enforcer state: decision and reason, plus an optional preview request
        and an optional command to send to the live system. Raise AsmError on anything
        inconsistent (it becomes an operational failure, never a verdict)."""
        ...

    # --- Commit on the live system ---
    def command_inputs(self, live: AsmState, command: Command) -> dict[str, str]:
        """Inputs of the single live-device step that applies the authorized command."""
        ...
    def same_target(self, left: Action, right: Action) -> bool:
        """True if two actions act on the same object (e.g. same dose). The enforcer may
        REPLACE the parameters of the requested action but never change its target."""
        ...
    def commit_applied(self, live: AsmState, command: Command) -> bool:
        """ACK check: does the live state prove the command was applied?"""
        ...
    def commit_rejected(self, live: AsmState, command: Command) -> bool:
        """ACK check: does the live state prove the device explicitly rejected the command?
        If neither applied nor rejected is proven, the gateway reports an operational failure."""
        ...

    # --- Preview: simulation of the whole plan on a replayed twin of the live system ---
    def action_inputs(self, current: AsmState, action: Action,
                      command_id: int) -> dict[str, str]:
        """Inputs of the twin-device step that executes `action` during a preview
        (same effect as `command_inputs`, but built from an action, not from an enforcer command)."""
        ...
    def preview_inputs(self, current: AsmState, phase: str,
                       request: PreviewRequest, action: Action | None = None,
                       command_id: int = 0,
                       goals: dict | None = None) -> dict[str, str]:
        """Inputs of one coordinator step. Phases, in order: `begin` (once, with the twin
        state), `inspect` (after each simulated action, `action` is the one just executed),
        `finalize` (once, with `goals` so the coordinator can check the user's constraints)."""
        ...
    def preview_output(self, state: AsmState) -> PreviewResult:
        """Decode the coordinator state after `finalize` into the preview verdict."""
        ...
