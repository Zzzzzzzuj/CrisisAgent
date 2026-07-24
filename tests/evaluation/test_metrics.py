from evaluation import metrics


def test_accuracy_and_fallback_metrics():
    case_results = [
        {"risk_match": True, "emotion_match": False, "tone_match": True, "fallback": True, "trace_duration_ms": 100},
        {"risk_match": False, "emotion_match": True, "tone_match": False, "fallback": False, "trace_duration_ms": 300},
    ]

    assert metrics.calculate_accuracy(case_results, "risk_match") == 0.5
    assert metrics.calculate_accuracy(case_results, "emotion_match") == 0.5
    assert metrics.calculate_accuracy(case_results, "tone_match") == 0.5
    assert metrics.calculate_fallback_rate(case_results) == 0.5
    assert metrics.calculate_average_duration_ms(case_results) == 200.0


def test_rag_metrics():
    case_results = [
        {
            "rag_enabled": True,
            "rag_hit": True,
            "rag_sources": ["food_safety.md", "legal_risk_rules.md"],
            "rag_source_count": 2,
        },
        {
            "rag_enabled": True,
            "rag_hit": False,
            "rag_sources": [],
            "rag_source_count": 0,
        },
        {
            "rag_enabled": False,
            "rag_hit": False,
            "rag_sources": [],
            "rag_source_count": 0,
        },
    ]

    assert metrics.calculate_rag_hit_rate(case_results) == 0.5
    assert metrics.calculate_average_retrieved_sources(case_results) == 1.0
    assert metrics.calculate_source_distribution(case_results) == {
        "food_safety.md": 1,
        "legal_risk_rules.md": 1,
    }


def test_retrieval_evaluation_metrics():
    case_results = [
        {
            "expected_sources": ["food_safety.md", "legal_risk_rules.md"],
            "rag_sources": ["food_safety.md", "crisis_response.md"],
            "rerank_gain": 1,
        },
        {
            "expected_sources": ["legal_risk_rules.md"],
            "rag_sources": ["crisis_response.md", "legal_risk_rules.md"],
            "rerank_gain": -1,
        },
    ]

    assert metrics.calculate_recall_at_k(case_results) == 0.75
    assert metrics.calculate_mrr(case_results) == 0.75
    assert metrics.calculate_average_rerank_gain(case_results) == 0.0


def test_rerank_rank_change():
    chunks = [
        {"source": "crisis_response.md", "score": 0.9, "rerank_score": 0.5},
        {"source": "legal_risk_rules.md", "score": 0.7, "rerank_score": 0.95},
    ]

    result = metrics.calculate_rerank_rank_change(["legal_risk_rules.md"], chunks)

    assert result == {
        "before_rank": 2,
        "after_rank": 1,
        "rerank_gain": 1,
    }


def test_category_metrics_summary():
    case_results = [
        {
            "category": "food_safety",
            "risk_match": True,
            "emotion_match": True,
            "tone_match": False,
            "fallback": True,
            "trace_duration_ms": 100,
            "rag_enabled": True,
            "rag_hit": True,
            "expected_sources": ["food_safety.md"],
            "rag_sources": ["food_safety.md"],
            "rag_source_count": 2,
            "rerank_gain": 1,
        },
        {
            "category": "food_safety",
            "risk_match": False,
            "emotion_match": True,
            "tone_match": True,
            "fallback": False,
            "trace_duration_ms": 300,
            "rag_enabled": True,
            "rag_hit": False,
            "expected_sources": ["food_safety.md"],
            "rag_sources": [],
            "rag_source_count": 0,
            "rerank_gain": 0,
        },
        {
            "category": "service_outage",
            "risk_match": True,
            "emotion_match": False,
            "tone_match": True,
            "fallback": False,
            "trace_duration_ms": 200,
            "rag_enabled": False,
            "rag_hit": False,
            "expected_sources": ["crisis_response.md"],
            "rag_sources": [],
            "rag_source_count": 0,
            "rerank_gain": 0,
        },
    ]

    summary = metrics.summarize_category_metrics(case_results)

    assert summary["food_safety"]["total_cases"] == 2
    assert summary["food_safety"]["risk_accuracy"] == 0.5
    assert summary["food_safety"]["emotion_accuracy"] == 1.0
    assert summary["food_safety"]["tone_accuracy"] == 0.5
    assert summary["food_safety"]["fallback_rate"] == 0.5
    assert summary["food_safety"]["average_duration_ms"] == 200.0
    assert summary["food_safety"]["rag_hit_rate"] == 0.5
    assert summary["food_safety"]["recall_at_k"] == 0.5
    assert summary["food_safety"]["mrr"] == 0.5
    assert summary["food_safety"]["average_rerank_gain"] == 0.5
    assert summary["food_safety"]["average_retrieved_sources"] == 1.0
    assert summary["service_outage"]["total_cases"] == 1
    assert summary["service_outage"]["risk_accuracy"] == 1.0
    assert summary["service_outage"]["rag_hit_rate"] == 0.0


def test_agent_metrics_summary():
    case_results = [
        {
            "trace": [
                {
                    "agent": "Agent A",
                    "name": "舆情分析 Agent",
                    "start_time": "2026-07-20T10:00:00+00:00",
                    "end_time": "2026-07-20T10:00:02+00:00",
                    "fallback": True,
                },
                {
                    "agent": "Agent E",
                    "name": "最终决策 Agent",
                    "start_time": "2026-07-20T10:00:02+00:00",
                    "end_time": "2026-07-20T10:00:03+00:00",
                    "fallback": False,
                },
            ]
        },
        {
            "trace": [
                {
                    "agent": "Agent A",
                    "name": "舆情分析 Agent",
                    "start_time": "2026-07-20T10:01:00+00:00",
                    "end_time": "2026-07-20T10:01:01+00:00",
                    "fallback": False,
                }
            ]
        },
    ]

    summary = metrics.summarize_agent_metrics(case_results)

    assert summary["Agent A"]["total_runs"] == 2
    assert summary["Agent A"]["average_duration_ms"] == 1500.0
    assert summary["Agent A"]["fallback_count"] == 1
    assert summary["Agent A"]["fallback_rate"] == 0.5
    assert summary["Agent E"]["total_runs"] == 1
