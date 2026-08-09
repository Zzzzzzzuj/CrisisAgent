from evaluation.rag_gate_v2_development import (
    GATE_V1_CHALLENGE_FN_IDS,
    evaluate_gate_cases,
    run_gate_v2_development_evaluation,
    summarize_gate_results,
    summarize_positive_category_tpr,
)


def test_evaluate_gate_cases_records_tp_and_tn():
    cases = [
        {"id": "pos", "query": "当前大量用户无法登录，订单处理中断"},
        {"id": "neg", "query": "查询产品维修网点"},
    ]

    positive = evaluate_gate_cases([cases[0]], "query", expected_need=True)
    negative = evaluate_gate_cases([cases[1]], "query", expected_need=False)

    assert positive[0]["gate_label"] == "TP"
    assert negative[0]["gate_label"] == "TN"


def test_summarize_gate_results_reports_confusion_matrix():
    results = [
        {"gate_label": "TP", "expected_need": True, "type": "positive"},
        {"gate_label": "FN", "expected_need": True, "type": "positive"},
        {"gate_label": "TN", "expected_need": False, "type": "hard_negative"},
        {"gate_label": "FP", "expected_need": False, "type": "hard_negative"},
    ]

    summary = summarize_gate_results(results)

    assert summary["TP"] == 1
    assert summary["TN"] == 1
    assert summary["FP"] == 1
    assert summary["FN"] == 1
    assert summary["tpr"] == 0.5
    assert summary["tnr"] == 0.5
    assert summary["hard_negative_reject_rate"] == 0.5


def test_positive_category_tpr_is_reported_per_category():
    results = [
        {"expected_need": True, "category": "food_safety", "gate_label": "TP"},
        {"expected_need": True, "category": "food_safety", "gate_label": "FN"},
        {"expected_need": True, "category": "data_privacy", "gate_label": "TP"},
    ]

    summary = summarize_positive_category_tpr(results)

    assert summary["food_safety"] == {"TP": 1, "FN": 1, "tpr": 0.5}
    assert summary["data_privacy"] == {"TP": 1, "FN": 0, "tpr": 1.0}


def test_gate_v2_development_result_keeps_challenge_v1_post_hoc_separate():
    result = run_gate_v2_development_evaluation()

    assert result["challenge_v1_usage"] == "post-hoc regression only"
    assert result["gate_v1_challenge_first_run"]["status"] == "FAIL"
    assert result["development"]["TP"] + result["development"]["FN"] == 15
    assert result["calibration"]["TN"] + result["calibration"]["FP"] == 24
    assert result["challenge_v1_post_hoc"]["TP"] + result["challenge_v1_post_hoc"]["FN"] == 20
    assert result["challenge_v1_post_hoc"]["TN"] + result["challenge_v1_post_hoc"]["FP"] == 20
    assert len(result["original_fn_v2_results"]) == len(GATE_V1_CHALLENGE_FN_IDS)
