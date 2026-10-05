from evaluation.p5_0_mock_workflow_baseline import build_baseline


def test_mock_baseline_uses_real_workflow_metrics_and_keeps_mock_limits_explicit():
    baseline = build_baseline()

    assert baseline["measurement_source"] == "run_dynamic_agent_default_registry_and_executor"
    assert baseline["performance_representative"] is False
    assert baseline["real_provider_performance_baseline"] is False
    assert baseline["mock_latency_is_real_provider_latency"] is False
    assert baseline["mock_tokens_are_provider_tokens"] is False
    assert baseline["mock_cost_is_production_cost"] is False
    assert [case["case_id"] for case in baseline["cases"]] == ["M1", "M2", "M3", "M4"]

    for case in baseline["cases"]:
        metrics = case["metrics"]
        assert sum(agent["execution_count"] for agent in metrics["agent_metrics"]) > 0
        assert metrics["context_chars_before"] > 0
        assert metrics["context_chars_after"] > 0
        assert metrics["token_source"] != "provider"
        assert case["performance_representative"] is False
        if "human_fact_request" in case["expected_observable_events"]:
            assert metrics["human_fact_request_count"] > 0

    assert baseline["cases"][0]["metrics"]["human_fact_request_count"] == 0
    assert all(case["runtime_state"] == "WAITING_HUMAN" for case in baseline["cases"][1:3])
    assert all("legal" in case["executed_agents"] for case in baseline["cases"][1:])
    assert all(case["metrics"]["retrieval_call_count"] == 0 for case in baseline["cases"][:3])

    assert baseline["totals"]["llm_calls"] == 0
    assert baseline["totals"]["retrieval_calls"] >= 1
    assert baseline["totals"]["human_fact_requests"] >= 1
    assert baseline["totals"]["tool_calls"] >= 0
    assert baseline["totals"]["cost_estimation_status"] == "unavailable"
    assert "mock LLM response" not in repr(baseline)
    assert "C:/Users/" not in repr(baseline)
