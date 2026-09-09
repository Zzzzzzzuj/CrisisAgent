from backend.api.memory_eval import run_memory_eval


def test_memory_eval_reports_relevance_budget_and_safety_metrics():
    result = run_memory_eval([
        {
            "fact_status": "verified",
            "top_public_signals": [1],
            "top_alerts": [],
            "top_legal_evidence": [],
            "related_case_memories": [{"memory_id": "m1"}],
            "dropped_fields": ["noise"],
        },
        {
            "fact_status": "unverified",
            "top_public_signals": list(range(6)),
            "top_alerts": [],
            "top_legal_evidence": [],
            "related_case_memories": [],
            "dropped_fields": [],
        },
    ])
    assert result["total_cases"] == 2
    assert result["memory_relevance"] == 0.5
    assert result["context_budget_compliance"] == 0.5
    assert result["critical_fact_coverage"] == 1.0
    assert result["dropped_noise_count"] == 1
