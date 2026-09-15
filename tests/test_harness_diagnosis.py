import pytest

from backend.diagnostics.failure_analyzer import analyze_trace_failure
from backend.evaluation.harness_comparison import compare_harnesses
from backend.harness.spec import build_default_harness_spec, spec_hash


def test_failure_analyzer_maps_rag_tool_context_and_review_tags():
    result = analyze_trace_failure(
        trace=[{
            "trace_id": "legal-1",
            "agent": "legal",
            "rag": {"retrieval_skipped": False, "evidence_quality": {"low_confidence": True, "quality": "low", "reasons": ["source_category_mismatch"], "context_pollution_rate": 0.9}},
            "tool_result": {"error_code": "TOOL_TIMEOUT"},
        }],
        review={"required": True},
        context_pack={"compression_level": "red", "dropped_fields": ["risk_level"]},
    )
    assert {"evidence_low_confidence", "evidence_conflict", "retrieval_low_quality", "tool_timeout", "review_required", "context_over_budget", "context_critical_field_dropped"} <= set(result["failure_tags"])


def test_failure_analyzer_does_not_report_clean_run():
    assert analyze_trace_failure(trace=[{"agent": "writer", "status": "success"}])["failure_tags"] == []


@pytest.mark.parametrize(("error_code", "tag"), [
    ("TOOL_TIMEOUT", "tool_timeout"),
    ("TOOL_RETRY_EXHAUSTED", "tool_retry_exhausted"),
    ("TOOL_OUTPUT_INVALID", "tool_output_invalid"),
    ("TOOL_LOOP_DETECTED", "tool_loop_detected"),
])
def test_failure_analyzer_maps_tool_error_codes(error_code, tag):
    result = analyze_trace_failure(tool_results=[{"error_code": error_code}])
    assert result["failure_tags"] == [tag]


def test_harness_comparison_uses_same_cases_and_hashes():
    baseline = build_default_harness_spec()
    candidate = build_default_harness_spec()
    candidate["metadata"]["version"] = "1.0.1"
    result = compare_harnesses(baseline, candidate, cases=[{"case_id": "case-1"}])
    assert result["same_case_ids"] == ["case-1"]
    assert result["baseline"]["spec_hash"] == spec_hash(baseline)
    assert result["candidate"]["spec_hash"] == spec_hash(candidate)
    assert result["delta"]["task_completion_rate"] == 0


def test_comparison_keeps_candidate_disabled_from_enablement():
    candidate = build_default_harness_spec()
    assert candidate["metadata"]["status"] == "active"
    assert analyze_trace_failure(trace=[])["recommended_harness_areas"] == []
