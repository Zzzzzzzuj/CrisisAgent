from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.skills.execution_budget import ToolExecutionBudget
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill
from backend.skills.tool_runner import (
    TOOL_DISABLED,
    TOOL_EXECUTION_FAILED,
    TOOL_FALLBACK_FAILED,
    TOOL_INPUT_INVALID,
    TOOL_LOOP_DETECTED,
    TOOL_NOT_FOUND,
    TOOL_OUTPUT_INVALID,
    TOOL_RETRY_EXHAUSTED,
    TOOL_TIMEOUT,
    ToolResult,
    ToolRunner,
)


@dataclass(frozen=True)
class ToolReliabilityCase:
    case_id: str
    description: str
    tool_name: str
    arguments: dict[str, Any]
    expected_success: bool
    expected_error_code: str | None = None
    expected_fallback_used: bool = False
    expected_human_review_required: bool = False


@dataclass(frozen=True)
class ToolReliabilityMetrics:
    total_cases: int
    success_cases: int
    failed_cases: int
    tool_success_rate: float
    tool_failure_rate: float
    retry_rate: float
    fallback_rate: float
    timeout_rate: float
    output_validation_failure_rate: float
    loop_detected_rate: float
    human_review_trigger_rate: float
    error_code_counts: dict[str, int] = field(default_factory=dict)


def load_cases(path: str | Path) -> list[ToolReliabilityCase]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Tool reliability cases must be a JSON array.")
    return [ToolReliabilityCase(**row) for row in rows]


def run_tool_reliability_eval(cases: list[ToolReliabilityCase]) -> dict[str, Any]:
    runner, state = _build_fake_runner()
    results = []
    for case in cases:
        result = _run_case(case, runner, state)
        results.append(_case_result(case, result))

    metrics = _calculate_metrics(results)
    return {
        "metrics": asdict(metrics),
        "cases": results,
        "offline": True,
        "real_network": False,
        "real_llm": False,
    }


def _run_case(case: ToolReliabilityCase, runner: ToolRunner, state: dict[str, int]) -> ToolResult:
    if case.case_id == "loop_detected":
        runner.run(case.tool_name, case.arguments)
        return runner.run(case.tool_name, case.arguments)
    return runner.run(case.tool_name, case.arguments)


def _case_result(case: ToolReliabilityCase, result: ToolResult) -> dict[str, Any]:
    actual = result.to_dict()
    expected_match = (
        result.success == case.expected_success
        and result.error_code == case.expected_error_code
        and result.fallback_used == case.expected_fallback_used
        and result.human_review_required == case.expected_human_review_required
    )
    return {
        "case_id": case.case_id,
        "description": case.description,
        "expected": {
            "success": case.expected_success,
            "error_code": case.expected_error_code,
            "fallback_used": case.expected_fallback_used,
            "human_review_required": case.expected_human_review_required,
        },
        "actual": actual,
        "expected_match": expected_match,
    }


def _calculate_metrics(results: list[dict[str, Any]]) -> ToolReliabilityMetrics:
    total = len(results)
    successful = sum(1 for item in results if item["actual"]["success"])
    failed = total - successful
    codes = {}
    for item in results:
        code = item["actual"].get("error_code")
        if code:
            codes[code] = codes.get(code, 0) + 1

    def rate(count: int) -> float:
        return round(count / total, 4) if total else 0.0

    return ToolReliabilityMetrics(
        total_cases=total,
        success_cases=successful,
        failed_cases=failed,
        tool_success_rate=rate(successful),
        tool_failure_rate=rate(failed),
        retry_rate=rate(sum(1 for item in results if item["actual"]["retry_count"] > 0)),
        fallback_rate=rate(sum(1 for item in results if item["actual"]["fallback_used"])),
        timeout_rate=rate(sum(1 for item in results if item["actual"]["error_code"] == TOOL_TIMEOUT)),
        output_validation_failure_rate=rate(sum(1 for item in results if item["actual"]["error_code"] == TOOL_OUTPUT_INVALID)),
        loop_detected_rate=rate(sum(1 for item in results if item["actual"]["error_code"] == TOOL_LOOP_DETECTED)),
        human_review_trigger_rate=rate(sum(1 for item in results if item["actual"]["human_review_required"])),
        error_code_counts=codes,
    )


def _build_fake_runner() -> tuple[ToolRunner, dict[str, int]]:
    state: dict[str, int] = {}

    def stable(_):
        return {"ok": True}

    def exception(_):
        raise RuntimeError("fake_handler_exception")

    def timeout(_):
        time.sleep(0.05)
        return {"ok": True}

    def retry_success(_):
        state["retry_success"] = state.get("retry_success", 0) + 1
        if state["retry_success"] == 1:
            raise RuntimeError("temporary_fake_failure")
        return {"ok": True}

    def retry_exhausted(_):
        raise RuntimeError("persistent_fake_failure")

    def invalid_output(_):
        return {"wrong": True}

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    def make(name, handler, **kwargs):
        enabled = kwargs.pop("enabled", True)
        return AgentSkill(
            name=name,
            description=f"Offline reliability fake: {name}",
            input_schema=input_schema,
            output_schema=schema,
            category="test",
            owner_agent="evaluation",
            safety_level="low",
            enabled=enabled,
            version="eval",
            handler=handler,
            **kwargs,
        )

    skills = [
        make("success_basic", stable),
        make("handler_exception", exception),
        make("timeout", timeout, timeout_ms=1),
        make("retry_success", retry_success, max_retries=1),
        make("retry_exhausted", retry_exhausted, max_retries=1),
        make("output_invalid", invalid_output),
        make("fallback_success", exception, fallback_policy="handler"),
        make("fallback_failed", exception, fallback_policy="handler"),
        make("disabled_tool", stable, enabled=False),
        make("loop_detected", stable),
    ]
    fallbacks = {
        "fallback_success": lambda _: {"ok": True},
        "fallback_failed": lambda _: {"wrong": True},
    }
    # Keep the global retry budget above the per-tool retry limit so the
    # retry_exhausted case exercises ToolRunner's own bounded retry result.
    budget = ToolExecutionBudget(max_steps=20, max_retries=10, max_same_call=1)
    return ToolRunner(SkillRegistry(skills), fallback_handlers=fallbacks, budget=budget), state
