from pathlib import Path

from backend.api.monitoring_eval import load_monitoring_eval_cases, run_monitoring_eval


def test_monitoring_eval_fixture_and_metrics_are_offline():
    cases = load_monitoring_eval_cases(Path(__file__).parents[1] / "data" / "monitoring_eval_cases.json")
    result = run_monitoring_eval(cases)
    assert result["total_cases"] == 6
    assert "mention_relevance" in result
    assert result["false_positive_count"] == 1
    assert result["failed_cases"]
    assert any(item["case_id"] == "signal_false_alert" for item in result["failed_cases"])
