import time

from backend.skills.builtins import create_default_registry
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill, ToolDefinition
from backend.skills.tool_runner import (
    TOOL_DISABLED,
    TOOL_EXECUTION_FAILED,
    TOOL_FALLBACK_FAILED,
    TOOL_INPUT_INVALID,
    TOOL_NOT_FOUND,
    TOOL_OUTPUT_INVALID,
    TOOL_POLICY_DENIED,
    TOOL_RETRY_EXHAUSTED,
    TOOL_TIMEOUT,
    ToolRunner,
)


def _tool(**overrides):
    values = dict(
        name="test_tool",
        description="A deterministic test tool.",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        category="test",
        owner_agent="test",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=lambda payload: {"ok": True},
    )
    values.update(overrides)
    return AgentSkill(**values)


def test_tool_definition_metadata_has_safe_defaults_and_serializes():
    definition = _tool()
    assert isinstance(definition, ToolDefinition)
    data = definition.to_dict()
    assert data["read_only"] is True
    assert data["risk_level"] == "low"
    assert data["requires_human_confirmation"] is False
    assert data["timeout_ms"] == 3000
    assert data["max_retries"] == 0
    assert data["fallback_policy"] == "none"


def test_default_registry_does_not_expose_sensitive_actions():
    names = {item["name"] for item in create_default_registry().list_skills(include_disabled=True)}
    assert not names.intersection({"approve", "reject", "publish", "final_publish", "send_notification", "delete_session", "modify_knowledge_base"})


def test_input_invalid_and_tool_not_found():
    runner = ToolRunner(SkillRegistry([_tool()]))
    assert runner.run("test_tool", {}).error_code == TOOL_INPUT_INVALID
    assert runner.run("missing", {"value": "x"}).error_code == TOOL_NOT_FOUND


def test_disabled_tool_is_blocked():
    result = ToolRunner(SkillRegistry([_tool(enabled=False)])).run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_DISABLED


def test_handler_exception_is_structured():
    def fail(_):
        raise RuntimeError("boom")

    result = ToolRunner(SkillRegistry([_tool(handler=fail)])).run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_EXECUTION_FAILED
    assert result.human_review_required is True


def test_timeout_is_structured():
    def slow(_):
        time.sleep(0.05)
        return {"ok": True}

    result = ToolRunner(SkillRegistry([_tool(handler=slow, timeout_ms=1)])).run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_TIMEOUT


def test_retry_then_success():
    calls = {"count": 0}

    def flaky(_):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return {"ok": True}

    result = ToolRunner(SkillRegistry([_tool(handler=flaky, max_retries=1)])).run("test_tool", {"value": "x"})
    assert result.success is True
    assert result.attempts == 2
    assert result.retry_count == 1


def test_retry_exhausted_and_trace_fields():
    result = ToolRunner(SkillRegistry([_tool(handler=lambda _: (_ for _ in ()).throw(RuntimeError("bad")), max_retries=1)])).run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_RETRY_EXHAUSTED
    assert {"attempts", "retry_count", "duration_ms", "error_code", "fallback_used", "success"}.issubset(result.trace)


def test_output_schema_failure():
    result = ToolRunner(SkillRegistry([_tool(handler=lambda _: {"wrong": True})])).run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_OUTPUT_INVALID


def test_fallback_success_and_fallback_failure():
    definition = _tool(fallback_policy="handler", handler=lambda _: (_ for _ in ()).throw(RuntimeError("primary")))
    runner = ToolRunner(SkillRegistry([definition]), fallback_handlers={"test_tool": lambda _: {"ok": True}})
    result = runner.run("test_tool", {"value": "x"})
    assert result.success is True
    assert result.fallback_used is True

    failed = ToolRunner(SkillRegistry([definition]), fallback_handlers={"test_tool": lambda _: {"wrong": True}}).run("test_tool", {"value": "x"})
    assert failed.error_code == TOOL_FALLBACK_FAILED


def test_policy_denied_requires_review():
    runner = ToolRunner(SkillRegistry([_tool(requires_human_confirmation=True)]))
    result = runner.run("test_tool", {"value": "x"})
    assert result.error_code == TOOL_POLICY_DENIED
    assert result.human_review_required is True
