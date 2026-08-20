import pytest

from backend.skills import create_default_registry
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


def test_default_registry_contains_builtin_skills():
    registry = create_default_registry()

    names = {skill["name"] for skill in registry.list_skills()}

    assert {
        "legal_rag_search",
        "session_lookup",
        "runtime_metrics_query",
        "guardrail_check",
        "knowledge_document_search",
    } <= names


def test_registry_rejects_duplicate_skill_name():
    skill = _skill("demo_skill")
    registry = SkillRegistry([skill])

    with pytest.raises(ValueError, match="already registered"):
        registry.register(skill)


def test_registry_validates_required_input_fields():
    registry = SkillRegistry([_skill("demo_skill")])

    with pytest.raises(ValueError, match="Missing required"):
        registry.validate_input("demo_skill", {})


def test_registry_execute_returns_tool_call_trace():
    registry = SkillRegistry([_skill("demo_skill")])

    result = registry.execute("demo_skill", {"query": "食品安全"})

    assert result.success is True
    assert result.output == {"ok": True, "query": "食品安全"}
    assert result.tool_call_trace["skill_name"] == "demo_skill"
    assert result.tool_call_trace["status"] == "success"


def test_disabled_skill_is_blocked():
    registry = SkillRegistry([_skill("disabled_skill", enabled=False)])

    result = registry.execute("disabled_skill", {"query": "食品安全"})

    assert result.success is False
    assert result.error == "skill_disabled"
    assert result.tool_call_trace["status"] == "blocked"


def _skill(name: str, enabled: bool = True) -> AgentSkill:
    return AgentSkill(
        name=name,
        description="Demo skill",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="demo",
        owner_agent="test",
        safety_level="low",
        enabled=enabled,
        version="1.0",
        handler=lambda payload: {"ok": True, "query": payload["query"]},
    )
