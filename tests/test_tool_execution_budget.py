from backend.skills.execution_budget import (
    TOOL_BUDGET_EXCEEDED,
    TOOL_LOOP_DETECTED,
    TOOL_RETRY_BUDGET_EXCEEDED,
    TOOL_RUNTIME_BUDGET_EXCEEDED,
    ToolExecutionBudget,
)
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill
from backend.skills.tool_runner import ToolRunner


def _tool(handler=None, **overrides):
    values = dict(
        name="budget_tool",
        description="Budget test tool",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        category="test",
        owner_agent="test",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=handler or (lambda _: {"ok": True}),
    )
    values.update(overrides)
    return AgentSkill(**values)


def test_default_budget_can_be_created_and_allows_first_call():
    budget = ToolExecutionBudget()
    result = budget.check("budget_tool", {"value": "x"})
    assert result.allowed is True
    assert result.error_code is None


def test_step_budget_is_enforced():
    budget = ToolExecutionBudget(max_steps=1)
    first = budget.check("budget_tool", {"value": "x"})
    budget.record("budget_tool", {"value": "x"}, 1, 1)
    second = budget.check("budget_tool", {"value": "y"})
    assert first.allowed is True
    assert second.error_code == TOOL_BUDGET_EXCEEDED


def test_retry_budget_is_enforced():
    budget = ToolExecutionBudget(max_retries=1)
    budget.record("budget_tool", {"value": "x"}, 1, 1)
    allowed = budget.check("budget_tool", {"value": "x"}, attempt=2)
    budget.record("budget_tool", {"value": "x"}, 1, 2)
    blocked = budget.check("budget_tool", {"value": "x"}, attempt=3)
    assert allowed.allowed is True
    assert blocked.error_code == TOOL_RETRY_BUDGET_EXCEEDED


def test_runtime_budget_is_enforced_with_injected_clock():
    clock = lambda: 6001
    budget = ToolExecutionBudget(max_runtime_ms=5000, started_at_ms=0, _clock_ms=clock)
    result = budget.check("budget_tool", {"value": "x"})
    assert result.error_code == TOOL_RUNTIME_BUDGET_EXCEEDED


def test_same_call_loop_is_detected_using_normalized_arguments():
    budget = ToolExecutionBudget(max_same_call=1)
    args_a = {"value": "x", "other": 1}
    args_b = {"other": 1, "value": "x"}
    budget.record("budget_tool", args_a, 1, 1)
    result = budget.check("budget_tool", args_b)
    assert result.error_code == TOOL_LOOP_DETECTED


def test_tool_runner_returns_loop_result_and_budget_trace():
    calls = {"count": 0}

    def handler(_):
        calls["count"] += 1
        return {"ok": True}

    budget = ToolExecutionBudget(max_same_call=1)
    runner = ToolRunner(SkillRegistry([_tool(handler=handler)]), budget=budget)
    first = runner.run("budget_tool", {"value": "x"})
    second = runner.run("budget_tool", {"value": "x"})
    assert first.success is True
    assert second.success is False
    assert second.error_code == TOOL_LOOP_DETECTED
    assert second.human_review_required is True
    assert second.trace["normalized_arguments_hash"]
    assert "budget_max_steps" in second.trace
    assert calls["count"] == 1


def test_tool_runner_step_budget_returns_structured_result():
    budget = ToolExecutionBudget(max_steps=1)
    runner = ToolRunner(SkillRegistry([_tool()]), budget=budget)
    assert runner.run("budget_tool", {"value": "a"}).success is True
    result = runner.run("budget_tool", {"value": "b"})
    assert result.success is False
    assert result.error_code == TOOL_BUDGET_EXCEEDED
    assert result.human_review_required is True
