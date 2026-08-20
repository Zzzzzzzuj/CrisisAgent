from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


JSONSchema = dict[str, Any]
SkillHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class AgentSkill:
    name: str
    description: str
    input_schema: JSONSchema
    output_schema: JSONSchema
    category: str
    owner_agent: str
    safety_level: str
    enabled: bool
    version: str
    handler: SkillHandler | None = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "category": self.category,
            "owner_agent": self.owner_agent,
            "safety_level": self.safety_level,
            "enabled": self.enabled,
            "version": self.version,
        }


@dataclass(frozen=True)
class SkillExecutionResult:
    skill_name: str
    success: bool
    output: dict[str, Any]
    error: str = ""
    tool_call_trace: dict[str, Any] = field(default_factory=dict)
