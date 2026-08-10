from backend.rag.schemas import RetrievalResult
from evaluation.rag_gate_challenge_evaluator import (
    DisabledFallbackRetriever,
    ACCEPTANCE_CRITERIA,
    empty_retrieval_result,
    evaluate_acceptance,
    evaluate_challenge_case,
    load_challenge_cases,
    normalize_case_for_retrieval,
    predict_gate,
    run_challenge_evaluation,
    summarize_gate_results,
)


def test_challenge_dataset_shape_is_frozen():
    cases = load_challenge_cases()
    positives = [case for case in cases if case["label"] == "need_rag"]
    negatives = [case for case in cases if case["label"] == "no_rag"]

    assert len(cases) == 40
    assert len(positives) == 20
    assert len(negatives) == 20
    assert _counts(positives, "category") == {
        "data_privacy": 4,
        "executive_misconduct": 4,
        "food_safety": 4,
        "product_quality": 4,
        "service_outage": 4,
    }
    assert _counts(negatives, "type") == {
        "business_non_crisis": 5,
        "hard_negative": 10,
        "unrelated": 5,
    }


def test_challenge_case_ids_are_unique():
    cases = load_challenge_cases()
    ids = [case["id"] for case in cases]

    assert len(ids) == len(set(ids))


def test_predict_gate_uses_only_event_field():
    captured = {}

    def fake_gate(**kwargs):
        captured.update(kwargs)
        return _gate_result(True)

    case = {
        "id": "case",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "food_safety",
        "event": "事件文本",
        "notes": "evaluation-only",
        "weak_explicit_crisis": True,
    }

    result = predict_gate(case, fake_gate)

    assert result["need_rag"] is True
    assert captured == {"event": "事件文本"}


def test_positive_case_normalization_uses_category_level_source_mapping():
    case = {
        "id": "case",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "data_privacy",
        "event": "用户个人信息风险",
        "notes": "",
    }

    normalized = normalize_case_for_retrieval(case)

    assert normalized["query"] == "用户个人信息风险"
    assert normalized["expected_hit"] is True
    assert normalized["acceptable_sources"] == ["data_privacy.md"]
    assert "food_safety.md" in normalized["forbidden_sources"]
    assert "data_privacy.md" not in normalized["forbidden_sources"]


def test_negative_case_normalization_has_no_acceptable_sources():
    case = {
        "id": "case",
        "label": "no_rag",
        "type": "hard_negative",
        "category": "hard_negative",
        "event": "隐私政策入口查询",
        "notes": "",
    }

    normalized = normalize_case_for_retrieval(case)

    assert normalized["expected_hit"] is False
    assert normalized["acceptable_sources"] == []
    assert normalized["forbidden_sources"]


def test_gate_false_returns_empty_retrieval_and_does_not_call_retriever():
    retriever = _CountingRetriever()
    case = _case("no_rag", "hard_negative", "hard_negative", "隐私政策入口在哪里")

    result = evaluate_challenge_case(case, retriever, lambda **kwargs: _gate_result(False))

    assert retriever.calls == 0
    assert result["retrieval"] == empty_retrieval_result()
    assert result["gate_label"] == "TN"


def test_gate_true_calls_retriever_and_records_real_sources():
    retriever = _CountingRetriever(source="data_privacy.md")
    case = _case("need_rag", "positive_crisis", "data_privacy", "用户信息泄露需要回应")

    result = evaluate_challenge_case(case, retriever, lambda **kwargs: _gate_result(True))

    assert retriever.calls == 1
    assert result["gate_label"] == "TP"
    assert result["metrics"]["retrieved_sources"] == ["data_privacy.md"]


def test_gate_summary_reports_confusion_and_breakdowns():
    cases = [
        {"label": "need_rag", "category": "food_safety", "gate_label": "TP"},
        {"label": "need_rag", "category": "food_safety", "gate_label": "FN"},
        {"label": "no_rag", "type": "hard_negative", "gate_label": "TN"},
        {"label": "no_rag", "type": "hard_negative", "gate_label": "FP"},
    ]

    summary = summarize_gate_results(cases)

    assert summary["TP"] == 1
    assert summary["TN"] == 1
    assert summary["FP"] == 1
    assert summary["FN"] == 1
    assert summary["tpr"] == 0.5
    assert summary["tnr"] == 0.5
    assert summary["hard_negative_reject_rate"] == 0.5
    assert summary["positive_by_category"]["food_safety"] == 0.5


def test_acceptance_uses_pre_registered_thresholds():
    gate_summary = {
        "tpr": ACCEPTANCE_CRITERIA["positive_tpr"],
        "tnr": ACCEPTANCE_CRITERIA["negative_tnr"],
        "hard_negative_reject_rate": ACCEPTANCE_CRITERIA["hard_negative_reject_rate"],
        "positive_by_category": {"food_safety": 1.0},
    }
    end_to_end_summary = {
        "recall_at_3": ACCEPTANCE_CRITERIA["recall_at_3"],
        "no_hit_accuracy": ACCEPTANCE_CRITERIA["no_hit_accuracy"],
    }

    result = evaluate_acceptance(gate_summary, end_to_end_summary)

    assert result["status"] == "PASS"
    assert all(result["checks"].values())


def test_acceptance_fails_when_domain_category_is_rejected_at_large_scale():
    gate_summary = {
        "tpr": 1.0,
        "tnr": 1.0,
        "hard_negative_reject_rate": 1.0,
        "positive_by_category": {"food_safety": 0.25},
    }
    end_to_end_summary = {"recall_at_3": 1.0, "no_hit_accuracy": 1.0}

    result = evaluate_acceptance(gate_summary, end_to_end_summary)

    assert result["status"] == "FAIL"
    assert result["checks"]["no_large_scale_positive_category_rejection"] is False


def test_disabled_fallback_retriever_raises_instead_of_faking_bge_success():
    retriever = DisabledFallbackRetriever()

    try:
        retriever.retrieve("query")
    except RuntimeError as exc:
        assert "Fallback is disabled" in str(exc)
    else:
        raise AssertionError("DisabledFallbackRetriever must raise.")


def test_run_challenge_evaluation_with_fake_retriever_does_not_need_bge(tmp_path):
    cases_path = tmp_path / "challenge.json"
    cases_path.write_text(
        """
[
  {
    "id": "pos_1",
    "label": "need_rag",
    "type": "positive_crisis",
    "category": "data_privacy",
    "event": "用户信息泄露需要回应",
    "notes": "positive"
  },
  {
    "id": "neg_1",
    "label": "no_rag",
    "type": "hard_negative",
    "category": "hard_negative",
    "event": "用户想查询隐私政策入口",
    "notes": "negative"
  }
]
""".strip(),
        encoding="utf-8",
    )

    result = run_challenge_evaluation(
        cases_path,
        retriever=_CountingRetriever(source="data_privacy.md"),
        gate_fn=lambda **kwargs: _gate_result("泄露" in kwargs["event"]),
        validate_dataset=False,
    )

    assert result["gate"]["TP"] == 1
    assert result["gate"]["TN"] == 1
    assert result["end_to_end"]["recall_at_3"] == 1.0
    assert result["end_to_end"]["no_hit_accuracy"] == 1.0


def _case(label, case_type, category, event):
    return {
        "id": "case",
        "label": label,
        "type": case_type,
        "category": category,
        "event": event,
        "notes": "",
    }


def _gate_result(need_rag):
    return {
        "need_rag": need_rag,
        "intent": "crisis_response_needed" if need_rag else "information_lookup",
        "decision_score": 3 if need_rag else -1,
        "reason": "test",
        "matched_signals": ["occurred_negative_event"] if need_rag else [],
        "negative_signals": [] if need_rag else ["information_lookup"],
    }


def _counts(cases, field):
    counts = {}
    for case in cases:
        counts[case[field]] = counts.get(case[field], 0) + 1
    return dict(sorted(counts.items()))


class _CountingRetriever:
    def __init__(self, source="data_privacy.md"):
        self.calls = 0
        self.source = source

    def retrieve(self, query, top_k=5):
        self.calls += 1
        return RetrievalResult(
            context="mock",
            chunks=[],
            sources=[
                {
                    "source": self.source,
                    "score": 0.8,
                    "rerank_score": 0.3,
                    "retrieval_type": "hybrid",
                    "retrieval_fallback": False,
                }
            ],
        )
