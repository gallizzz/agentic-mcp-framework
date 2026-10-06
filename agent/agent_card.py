"""
Agent Card specification and A2A Contract validation.
Provides dynamic discovery, MCP configuration extraction, and runtime
schema enforcement based on agent-card.json contracts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("agent_card")


class SkillDefinition(BaseModel):
    """
    Specification of a single capability (skill/tool) exposed by an agent.
    """
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    returns: Optional[Dict[str, Any]] = None


class SanitiseContractResult(BaseModel):
    """
    Pydantic contract enforcement for AsmetaS sanitise_action output,
    strictly validating against the returns specification in agent-card.json.
    """
    verdict: Literal["APPROVED", "VIOLATION"]
    input_action: Optional[str] = None
    sanitised_action: Optional[str] = None
    feedback: str
    raw_output: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentCard(BaseModel):
    """
    A2A (Agent-to-Agent) contract descriptor defining an agent's identity,
    runtime characteristics, communication protocol, and exposed skills.
    """
    name: str
    description: Optional[str] = None
    type: str = "deterministic"
    protocol: str = "mcp"
    transport: str = "stdio"
    entrypoint: str
    skills: List[SkillDefinition] = Field(default_factory=list)

    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """
        Retrieves a skill definition by name.
        """
        for s in self.skills:
            if s.name == skill_name:
                return s
        return None

    def to_mcp_server_config(self, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Derives the MCP server client configuration directly from the Agent Card entrypoint
        and transport definitions.
        """
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
        """
        Verifies that all skills declared in the Agent Card are actually exposed
        by the instantiated MCP server. Returns a list of missing skill names.
        """
        tool_names = set()
        for t in mcp_tools:
            if hasattr(t, "name"):
                tool_names.add(t.name)
            elif isinstance(t, dict) and "name" in t:
                tool_names.add(t["name"])

        declared_skills = {s.name for s in self.skills}
        missing_skills = [s for s in declared_skills if s not in tool_names]

        if missing_skills:
            logger.warning(
                f"Agent Card '{self.name}' declares skills not found in MCP server: {missing_skills}"
            )
        else:
            logger.info(
                f"Agent Card '{self.name}' successfully verified: all {len(declared_skills)} skills matched."
            )
        return missing_skills


def load_agent_card(file_path: Union[str, Path]) -> AgentCard:
    """
    Loads and validates an agent card from a JSON file.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Agent card not found at: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return AgentCard.model_validate(data)
