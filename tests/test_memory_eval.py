from backend.api.memory_eval import run_memory_eval


def test_memory_eval_reports_relevance_budget_and_safety_metrics():
    result = run_memory_eval([
        {
            "fact_status": "verified",
            "event_status": "current",
            "risk_level": "low",
            "top_public_signals": [1],
            "top_alerts": [],
            "top_legal_evidence": [],
            "related_case_memories": [{"memory_id": "m1"}],
            "dropped_fields": [{"field": "noise", "reason": "test", "dropped_count": 1}],
            "compression_level": "green",
            "target_agent": "writer",
            "agent_specific_focus": {"previous_statement_summary": "上一轮摘要"},
        },
        {
            "fact_status": "unverified",
            "event_status": "uncertain",
            "risk_level": "high",
            "top_public_signals": list(range(6)),
            "top_alerts": [],
            "top_legal_evidence": [],
            "related_case_memories": [],
            "dropped_fields": [],
            "compression_level": "red",
            "usage_ratio": 1.2,
        },
    ])
    assert result["total_cases"] == 2
    assert result["memory_relevance"] == 0.5
    assert result["context_budget_compliance"] == 0.5
    assert result["critical_fact_coverage"] == 1.0
    assert result["dropped_noise_count"] == 1
    assert result["compression_level_distribution"] == {"green": 1, "red": 1}
    assert result["over_budget_count"] == 1
    assert result["preserved_critical_fields_rate"] == 1.0
    assert result["dropped_fields_trace_coverage"] == 1.0
    assert result["agent_specific_preserved_rate"]["writer"] == 1.0
