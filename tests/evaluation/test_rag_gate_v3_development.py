from evaluation.rag_gate_v3_development import (
    GATE_V2_CHALLENGE_V2_FP_IDS,
    build_markdown_report,
    evaluate_gate_cases,
    run_gate_v3_development_evaluation,
    summarize_gate_results,
)


def test_evaluate_gate_cases_records_v3_explainability_fields():
    cases = [
        {
            "id": "current_incident",
            "event": "当前大量用户无法登录，平台需要立即整理对外回应。",
            "label": "need_rag",
        }
    ]

    result = evaluate_gate_cases(
        cases,
        text_field="event",
        expected_need=lambda case: case["label"] == "need_rag",
    )[0]

    assert result["gate_label"] == "TP"
    assert result["current_incident"] is True
    assert result["current_incident_signals"]
    assert result["task_intent"]
    assert result["decision_path"] == "current_incident_override"


def test_summarize_gate_results_reports_hard_negative_reject_rate():
    results = [
        {"gate_label": "TP", "expected_need": True, "type": "positive_crisis"},
        {"gate_label": "TN", "expected_need": False, "type": "hard_negative"},
        {"gate_label": "FP", "expected_need": False, "type": "hard_negative"},
        {"gate_label": "TN", "expected_need": False, "type": "business_non_crisis"},
    ]

    summary = summarize_gate_results(results)

    assert summary["TP"] == 1
    assert summary["TN"] == 2
    assert summary["FP"] == 1
    assert summary["FN"] == 0
    assert summary["tnr"] == 0.6667
    assert summary["hard_negative_reject_count"] == 1
    assert summary["hard_negative_reject_rate"] == 0.5


def test_gate_v3_development_keeps_challenges_post_hoc_only():
    result = run_gate_v3_development_evaluation()

    assert result["challenge_v1_usage"] == "post-hoc regression only"
    assert result["challenge_v2_usage"] == "post-hoc regression only"
    assert result["gate_v1_challenge_v1_first_run"]["status"] == "FAIL"
    assert result["gate_v2_challenge_v2_first_run"]["status"] == "FAIL"
    assert result["development"]["TP"] + result["development"]["FN"] == 15
    assert result["calibration"]["TN"] + result["calibration"]["FP"] == 24
    assert result["challenge_v1_post_hoc"]["TP"] + result["challenge_v1_post_hoc"]["FN"] == 20
    assert result["challenge_v2_post_hoc"]["TP"] + result["challenge_v2_post_hoc"]["FN"] == 20


def test_gate_v3_reports_original_challenge_v2_false_positive_recovery():
    result = run_gate_v3_development_evaluation()
    original_ids = {
        item["case_id"] for item in result["original_challenge_v2_fp_v3_results"]
    }

    assert original_ids == GATE_V2_CHALLENGE_V2_FP_IDS
    assert result["recovered_false_positives"] == 4
    assert result["remaining_false_positives"] == 0
    assert result["new_false_positive_count"] == 0
    assert result["new_false_negative_count"] == 0


def test_gate_v3_report_preserves_first_run_failure_history():
    report = build_markdown_report(run_gate_v3_development_evaluation())

    assert "Gate v1 Challenge v1 FIRST RUN: `FAIL`" in report
    assert "Gate v2 Challenge v2 FIRST RUN: `FAIL`" in report
    assert "post-hoc regression only" in report
    assert "must not be described as independent validation" in report
