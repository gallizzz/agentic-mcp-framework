"""The agent card module.

Agent Card specification and contract validator for A2A MCP services."""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field
logger = logging.getLogger("agent_card")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_agent_card(file_path: Union[str, Path]) -> AgentCard:
    """Loads and validates an Agent Card from a JSON file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Agent Card not found at: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return AgentCard.model_validate(data)

# ============================================================================
# SCHEMA MODELS
# ============================================================================

class SkillDefinition(BaseModel):
    """Specification of a capability (skill/tool) exposed by an agent."""
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    returns: Optional[Dict[str, Any]] = None

class SanitiseContractResult(BaseModel):
    """Pydantic contract enforcement for AsmetaS sanitise_action output."""
    verdict: Literal["APPROVED", "VIOLATION", "ERROR"]
    input_action: Optional[str] = None
    sanitised_action: Optional[str] = None
    feedback: str = ""
    raw_output: Optional[Dict[str, Any]] = Field(default_factory=dict)

# ============================================================================
# AGENT CARD CLASS
# ============================================================================

class AgentCard(BaseModel):
    """A2A (Agent-to-Agent) contract descriptor."""
    name: str
    description: Optional[str] = None
    type: str = "deterministic"
    protocol: str = "mcp"
    transport: str = "stdio"
    entrypoint: Union[str, Dict[str, Any]]
    skills: List[SkillDefinition] = Field(default_factory=list)

    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """Retrieves a skill definition by name."""
        for skill in self.skills:
            if skill.name == skill_name:
                return skill
        return None

    def to_mcp_server_config(self, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Derives MCP client configuration directly from the Agent Card entrypoint."""
        if isinstance(self.entrypoint, dict):
            command = str(self.entrypoint.get("command", ""))
            args = list(self.entrypoint.get("args", []))
        else:
            tokens = self.entrypoint.strip().split()
            if not tokens:
                raise ValueError(f"Invalid entrypoint in Agent Card: '{self.entrypoint}'")
            command = tokens[0]
            args = tokens[1:]

        config: Dict[str, Any] = {
            "command": command,
            "args": args,
            "transport": self.transport,
        }
        if env:
            config["env"] = env
        return config

    def validate_mcp_tools(self, mcp_tools: list) -> List[str]:
        """Verifies that all skills declared in the Agent Card are exposed by the server."""
        tool_names = {
            t.name if hasattr(t, "name") else t.get("name")
            for t in mcp_tools
            if hasattr(t, "name") or (isinstance(t, dict) and "name" in t)
        }

        declared_skills = {s.name for s in self.skills}
        missing_skills = [s for s in declared_skills if s not in tool_names]

        if missing_skills:
            logger.warning(
                f"Agent Card '{self.name}' declares missing skills: {missing_skills}"
            )
        else:
            logger.info(
                f"Agent Card '{self.name}' verified: all {len(declared_skills)} skills matched."
            )
        return missing_skills