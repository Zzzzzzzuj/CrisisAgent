from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.skills.skill_schema import AgentSkill, SkillExecutionResult


class SkillRegistry:
    def __init__(self, skills: list[AgentSkill] | None = None):
        self._skills: dict[str, AgentSkill] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: AgentSkill) -> None:
        if not skill.name:
            raise ValueError("Skill name is required.")
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> AgentSkill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def list_skills(self, include_disabled: bool = False) -> list[dict[str, Any]]:
        return [
            skill.to_dict()
            for skill in self._skills.values()
            if include_disabled or skill.enabled
        ]

    def validate_input(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        skill = self.get(name)
        return validate_json_schema_payload(skill.input_schema, payload)

    def execute(self, name: str, payload: dict[str, Any]) -> SkillExecutionResult:
        skill = self.get(name)
        trace = {
            "skill_name": name,
            "category": skill.category,
            "owner_agent": skill.owner_agent,
            "safety_level": skill.safety_level,
            "version": skill.version,
            "enabled": skill.enabled,
        }
        if not skill.enabled:
            return SkillExecutionResult(
                skill_name=name,
                success=False,
                output={},
                error="skill_disabled",
                tool_call_trace={**trace, "status": "blocked"},
            )
        try:
            validated = self.validate_input(name, payload)
            if skill.handler is None:
                raise RuntimeError("skill_handler_missing")
            output = skill.handler(validated)
            return SkillExecutionResult(
                skill_name=name,
                success=True,
                output=output,
                tool_call_trace={**trace, "status": "success"},
            )
        except Exception as exc:
            return SkillExecutionResult(
                skill_name=name,
                success=False,
                output={},
                error=str(exc),
                tool_call_trace={**trace, "status": "failed", "error": str(exc)},
            )


def validate_json_schema_payload(schema: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Skill input must be a JSON object.")
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    additional_allowed = schema.get("additionalProperties", True)

    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Missing required skill input fields: {missing}")

    if not additional_allowed:
        unknown = [field for field in payload if field not in properties]
        if unknown:
            raise ValueError(f"Unknown skill input fields: {unknown}")

    validated = deepcopy(payload)
    for field, field_schema in properties.items():
        if field not in validated:
            continue
        _validate_type(field, validated[field], field_schema.get("type"))
    return validated


def _validate_type(field: str, value: Any, expected_type: str | None) -> None:
    if expected_type is None:
        return
    checks = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    expected = checks.get(expected_type)
    if expected is None:
        return
    if expected_type == "integer" and isinstance(value, bool):
        raise ValueError(f"Field {field} must be integer.")
    if expected_type == "number" and isinstance(value, bool):
        raise ValueError(f"Field {field} must be number.")
    if not isinstance(value, expected):
        raise ValueError(f"Field {field} must be {expected_type}.")
