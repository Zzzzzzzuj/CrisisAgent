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


def test_category_metrics_summary():
    case_results = [
        {
            "category": "food_safety",
            "risk_match": True,
            "emotion_match": True,
            "tone_match": False,
            "fallback": True,
            "trace_duration_ms": 100,
        },
        {
            "category": "food_safety",
            "risk_match": False,
            "emotion_match": True,
            "tone_match": True,
            "fallback": False,
            "trace_duration_ms": 300,
        },
        {
            "category": "service_outage",
            "risk_match": True,
            "emotion_match": False,
            "tone_match": True,
            "fallback": False,
            "trace_duration_ms": 200,
        },
    ]

    summary = metrics.summarize_category_metrics(case_results)

    assert summary["food_safety"]["total_cases"] == 2
    assert summary["food_safety"]["risk_accuracy"] == 0.5
    assert summary["food_safety"]["emotion_accuracy"] == 1.0
    assert summary["food_safety"]["tone_accuracy"] == 0.5
    assert summary["food_safety"]["fallback_rate"] == 0.5
    assert summary["food_safety"]["average_duration_ms"] == 200.0
    assert summary["service_outage"]["total_cases"] == 1
    assert summary["service_outage"]["risk_accuracy"] == 1.0


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
