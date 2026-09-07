import json
from pathlib import Path

from evaluation.tool_reliability import load_cases, run_tool_reliability_eval


CASES = Path("data/tool_reliability_cases.json")


def test_tool_reliability_cases_load():
    cases = load_cases(CASES)
    assert len(cases) == 12
    assert {case.case_id for case in cases} == {
        "success_basic", "input_invalid", "handler_exception", "timeout",
        "retry_success", "retry_exhausted", "output_invalid", "fallback_success",
        "fallback_failed", "loop_detected", "disabled_tool", "tool_not_found",
    }


def test_offline_tool_reliability_eval_reports_metrics_and_matches_expectations():
    report = run_tool_reliability_eval(load_cases(CASES))
    metrics = report["metrics"]
    assert metrics["total_cases"] == 12
    assert metrics["success_cases"] == 3
    assert metrics["failed_cases"] == 9
    assert metrics["retry_rate"] > 0
    assert metrics["fallback_rate"] > 0
    assert metrics["timeout_rate"] > 0
    assert metrics["output_validation_failure_rate"] > 0
    assert metrics["loop_detected_rate"] > 0
    assert metrics["human_review_trigger_rate"] > 0
    assert metrics["error_code_counts"]["TOOL_LOOP_DETECTED"] == 1
    assert all(item["expected_match"] for item in report["cases"])
    assert report["offline"] is True
    assert report["real_network"] is False
    assert report["real_llm"] is False


def test_case_report_contains_actual_tool_result_trace():
    report = run_tool_reliability_eval(load_cases(CASES))
    retry = next(item for item in report["cases"] if item["case_id"] == "retry_success")
    assert retry["actual"]["retry_count"] > 0
    assert "duration_ms" in retry["actual"]["trace"]

