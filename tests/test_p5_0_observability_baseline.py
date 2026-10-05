from evaluation.p5_0_observability_baseline import build_baseline


def test_frozen_observability_baseline_is_safe_and_explicitly_synthetic():
    baseline = build_baseline()

    assert [case["case_id"] for case in baseline["cases"]] == ["O1", "O2", "O3", "O4", "O5", "O6"]
    assert baseline["data_kind"] == "synthetic_safe_instrumentation_fixtures"
    assert baseline["performance_interpretation"] == "instrumentation_only_not_real_workflow_or_provider_performance"
    assert baseline["totals"]["llm_calls"] == 2
    assert baseline["totals"]["retrieval_calls"] == 1
    assert baseline["totals"]["tool_calls"] == 1
    assert baseline["totals"]["fallback_cases"] == ["O5"]
    assert baseline["totals"]["human_gate_cases"] == ["O3", "O4"]
    assert baseline["token_reduction"] == "NOT_CLAIMED"
    assert baseline["cost_reduction"] == "NOT_CLAIMED"
    assert baseline["latency_improvement"] == "NOT_CLAIMED"
    assert "test-key" not in repr(baseline)
