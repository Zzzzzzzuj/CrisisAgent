from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.skills.builtins import create_default_registry
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill, SkillExecutionResult


def skill_to_openai_tool_schema(skill: AgentSkill) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": skill.name,
            "description": skill.description,
            "parameters": skill.input_schema,
        },
    }


def registry_to_openai_tools(registry: SkillRegistry) -> list[dict[str, Any]]:
    return [
        skill_to_openai_tool_schema(registry.get(skill["name"]))
        for skill in registry.list_skills()
    ]


class FunctionCallingAdapter:
    def __init__(self, registry: SkillRegistry | None = None):
        self.registry = registry or create_default_registry()

    def list_tools(self) -> list[dict[str, Any]]:
        return registry_to_openai_tools(self.registry)

    def validate_input(self, skill_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.registry.validate_input(skill_name, arguments)

    def execute_tool_call(
        self,
        skill_name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        result = self.registry.execute(skill_name, arguments)
        trace = _tool_call_trace(
            result=result,
            call_id=call_id,
            started_at=started_at,
            ended_at=_utc_now(),
        )
        return {
            "tool_call_id": call_id or "",
            "name": skill_name,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "tool_call_trace": trace,
        }


def _tool_call_trace(
    result: SkillExecutionResult,
    call_id: str | None,
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    return {
        **result.tool_call_trace,
        "tool_call_id": call_id or "",
        "started_at": started_at,
        "ended_at": ended_at,
        "success": result.success,
        "fallback_used": False,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
