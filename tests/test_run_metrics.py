from backend.observability.run_metrics import build_run_metrics
from backend.core.trace_safety import context_pack_trace_metadata
from backend.core.state import AgentState


def test_run_metrics_aggregate_safe_execution_retrieval_tool_and_human_signals():
    metrics = build_run_metrics("s-1", [
        {"agent": "legal", "status": "success", "duration_ms": 12.5,
         "llm_calls": [{"latency_ms": 4, "token_source": "provider", "input_tokens": 10,
                        "output_tokens": 3, "total_tokens": 13, "fallback_used": False}],
         "rag": {"retrieval_executed": True, "retrieval_latency_ms": 2.5,
                 "retrieval_status": "executed_with_hits"},
         "skills": {"results": [{"success": True, "trace": {"duration_ms": 1.5}}]},
         "context_pack": {"chars_before": 100, "chars_after": 60, "budget_chars": 80,
                          "truncated": True}},
        {"agent": "human_fact", "action": "REQUEST_HUMAN_FACT_VERIFICATION", "status": "success"},
        {"agent": "human_fact", "action": "HUMAN_FACT_RESPONSE", "status": "success"},
        {"agent": "human_gate", "status": "waiting_human"},
        {"agent": "human_gate", "status": "approved"},
    ], "COMPLETED")

    assert metrics["total_latency_ms"] == 12.5
    assert metrics["llm_call_count"] == 1
    assert metrics["token_source"] == "provider"
    assert metrics["total_tokens"] == 13
    assert metrics["retrieval_call_count"] == 1
    assert metrics["retrieval_status_counts"] == {"SUCCESS": 1}
    assert metrics["tool_call_count"] == 1
    assert metrics["tool_status_counts"] == {"SUCCESS": 1}
    assert metrics["context_chars_before"] == 100
    assert metrics["context_chars_after"] == 60
    assert metrics["context_truncated"] is True
    assert metrics["human_fact_request_count"] == 1
    assert metrics["human_fact_response_count"] == 1
    assert metrics["final_review_count"] == 1
    assert metrics["approval_count"] == 1
    assert metrics["human_intervention_count"] == 4


def test_missing_provider_usage_is_not_reported_as_real_tokens():
    metrics = build_run_metrics("s-2", [{"agent": "writer", "duration_ms": 1,
        "llm_calls": [{"latency_ms": 1, "token_source": "estimated", "estimated_tokens": 99}]}], "COMPLETED")

    assert metrics["token_source"] == "estimated"
    assert metrics["estimated_total_tokens"] == 99
    assert metrics["input_tokens"] is None
    assert metrics["output_tokens"] is None
    assert metrics["total_tokens"] is None


def test_operation_metrics_preserve_logical_call_retry_and_provider_usage_relationships():
    metrics = build_run_metrics("s-ops", [{"agent": "legal", "llm_calls": [{
        "llm_call_id": "a" * 32, "operation_type": "legal.claim_extraction",
        "operation_span_id": "b" * 32, "latency_ms": 40, "success": True,
        "http_attempt_count": 2, "retry_count": 1, "token_source": "provider",
        "input_tokens": 11, "output_tokens": 9, "total_tokens": 20,
        "attempts": [
            {"attempt_index": 0, "attempt_latency_ms": 18, "attempt_status": "TIMEOUT"},
            {"attempt_index": 1, "attempt_latency_ms": 20, "attempt_status": "SUCCESS"},
        ],
    }]}], "COMPLETED")

    assert metrics["operation_metrics"] == [{
        "operation_type": "legal.claim_extraction", "operation_span_count": 1,
        "logical_call_count": 1, "http_attempt_count": 2, "technical_retry_count": 1,
        "success_count": 1, "failure_count": 0, "latency_ms": 40.0,
        "attempt_status_counts": {"TIMEOUT": 1, "SUCCESS": 1},
        "provider_input_tokens": 11, "provider_output_tokens": 9,
        "provider_total_tokens": 20, "token_source": "provider",
    }]


def test_unrecognized_operation_type_is_aggregated_as_unknown_without_raw_label():
    metrics = build_run_metrics("s-unknown", [{"agent": "legal", "llm_calls": [{
        "operation_type": "legal.claim_extraction:PRIVATE TEXT", "latency_ms": 3,
        "http_attempt_count": 1, "retry_count": 0, "success": False,
        "token_source": "estimated", "estimated_tokens": 99,
    }]}], "COMPLETED")

    assert metrics["operation_metrics"][0]["operation_type"] == "unknown"
    assert "PRIVATE TEXT" not in repr(metrics)
    assert metrics["operation_metrics"][0]["token_source"] == "unavailable"
    assert metrics["operation_metrics"][0]["provider_total_tokens"] is None


def test_context_pack_trace_reports_characters_not_tokens():
    observed = context_pack_trace_metadata({
        "target_agent": "legal", "pre_compression_estimated_chars": 1000,
        "rendered_context": "x" * 600, "token_budget_hint": 800, "budget_unit": "characters",
        "dropped_fields": [{"field": "optional", "dropped_count": 1}],
    })

    assert observed["chars_before"] == 1000
    assert observed["chars_after"] == 600
    assert observed["reduction_chars"] == 400
    assert observed["reduction_ratio"] == 0.4
    assert observed["budget_chars"] == 800
    assert observed["truncated"] is True
    assert "tokens" not in observed


def test_targeted_retrieval_and_fallback_statuses_are_aggregated():
    metrics = build_run_metrics("s-retrieval", [{"agent": "legal", "duration_ms": 4,
        "rag": {"actions": [{"executed_action": "RETRIEVE_LEGAL_EVIDENCE", "status": "success",
                              "latency_ms": 2.5},
                             {"executed_action": "RETRIEVE_LEGAL_EVIDENCE", "status": "failed",
                              "latency_ms": 1.5, "fallback_used": True}]},
        "skills": {"results": [{"success": False, "fallback_used": True,
                                  "trace": {"duration_ms": 3, "fallback_used": True}}]}}], "COMPLETED")

    assert metrics["retrieval_call_count"] == 2
    assert metrics["retrieval_latency_ms"] is None
    assert metrics["retrieval_latency_status"] == "unavailable"
    assert metrics["retrieval_status_counts"] == {"SUCCESS": 1, "FALLBACK": 1}
    assert metrics["fallback_count"] == 2
    assert metrics["tool_status_counts"] == {"FALLBACK": 1}


def test_metrics_ignore_sensitive_trace_content_and_pricing_is_unavailable():
    metrics = build_run_metrics("s-3", [{"agent": "writer", "duration_ms": 1,
        "prompt": "PRIVATE PROMPT", "event": "PRIVATE EVENT",
        "llm_calls": [{"latency_ms": 1, "token_source": "unavailable", "prompt": "PRIVATE PROMPT",
                       "api_key": "test-key", "authorization": "Bearer test-key"}],
        "evidence": "PRIVATE EVIDENCE", "human_fact": "PRIVATE FACT"}], "COMPLETED")
    serialized = repr(metrics)

    for value in ("PRIVATE PROMPT", "PRIVATE EVENT", "PRIVATE EVIDENCE", "PRIVATE FACT", "test-key", "Bearer"):
        assert value not in serialized
    assert metrics["estimated_cost"] is None
    assert metrics["cost_estimation_status"] == "unavailable"


def test_observability_aggregation_failure_does_not_change_executor_result(monkeypatch):
    from backend.core.executor import execute

    monkeypatch.setattr("backend.observability.run_metrics.build_run_metrics",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("metrics unavailable")))
    state = {"session_id": "s-safe", "event": "fixture"}
    result = execute({"plan_id": "p", "plan": [{"agent": "writer", "reason": "test"}]}, state,
                     agent_registry={"writer": lambda payload: {"statement": "safe"}})

    assert result["results"]["writer"] == {"statement": "safe"}
    assert result["failed_agents"] == []
    assert result["execution_trace"][0]["status"] == "success"


def test_executor_persists_derived_metrics_on_existing_session_state():
    from backend.core.executor import execute

    state = AgentState(session_id="persisted", plan_id="p", event="fixture")
    execute({"plan_id": "p", "plan": [{"agent": "writer", "reason": "test"}]}, state,
            agent_registry={"writer": lambda payload: {"statement": "safe"}})

    assert state.metadata["run_metrics"]["session_id"] == "persisted"
    assert state.metadata["run_metrics"]["agent_metrics"][0]["agent_name"] == "writer"
