from pathlib import Path

import pytest

from backend.rag.schemas import RetrievalResult
from evaluation.rag_gate_challenge_v3_evaluator import (
    ACCEPTANCE_CRITERIA,
    CHALLENGE_PATH,
    PROTOCOL_PATH,
    DisabledFallbackRetriever,
    empty_retrieval_result,
    evaluate_acceptance,
    evaluate_challenge_case,
    load_challenge_cases,
    run_challenge_evaluation,
    summarize_gate_results,
)


def test_challenge_v3_dataset_shape_is_frozen():
    cases = load_challenge_cases()

    positives = [case for case in cases if case["label"] == "need_rag"]
    negatives = [case for case in cases if case["label"] == "no_rag"]

    assert len(cases) == 40
    assert len(positives) == 20
    assert len(negatives) == 20
    assert _count_by(positives, "category") == {
        "data_privacy": 4,
        "executive_misconduct": 4,
        "food_safety": 4,
        "product_quality": 4,
        "service_outage": 4,
    }
    assert _count_by(negatives, "type") == {
        "business_non_crisis": 4,
        "hard_negative": 12,
        "unrelated": 4,
    }


def test_challenge_v3_case_ids_are_unique():
    cases = load_challenge_cases()
    ids = [case["id"] for case in cases]

    assert len(ids) == len(set(ids))


def test_hard_negative_intent_type_coverage_is_recorded():
    cases = load_challenge_cases()
    hard_negatives = [case for case in cases if case["type"] == "hard_negative"]
    intent_types = {case["intent_type"] for case in hard_negatives}

    assert len(hard_negatives) == 12
    assert {
        "preparedness",
        "historical_analysis",
        "statistics_reporting",
        "training_learning",
        "content_editing",
        "policy_learning",
        "lookup",
        "customer_service",
        "future_hypothetical",
        "template_writing",
        "trend_analysis",
    } <= intent_types


def test_current_incident_observation_fields_are_present():
    cases = load_challenge_cases()
    positives = [case for case in cases if case["label"] == "need_rag"]

    assert sum(1 for case in positives if case.get("weak_current_incident")) >= 12
    assert sum(1 for case in positives if case.get("current_incident_with_task_word")) >= 12


def test_evaluator_passes_only_event_to_gate():
    case = {
        "id": "case_1",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "data_privacy",
        "event": "用户看到其他账号信息，平台需要回应。",
        "notes": "evaluation only",
        "weak_current_incident": True,
    }
    received_kwargs = {}

    def gate_fn(**kwargs):
        received_kwargs.update(kwargs)
        return _gate_result(True)

    evaluate_challenge_case(case, _FakeRetriever(), gate_fn)

    assert received_kwargs == {"event": case["event"]}
    assert "label" not in received_kwargs
    assert "type" not in received_kwargs
    assert "category" not in received_kwargs
    assert "notes" not in received_kwargs


def test_tp_tn_fp_fn_summary_and_hard_negative_reject_are_correct():
    summary = summarize_gate_results(
        [
            _case("need_rag", "positive_crisis", "food_safety", "TP"),
            _case("need_rag", "positive_crisis", "food_safety", "FN"),
            _case("no_rag", "hard_negative", "hard_negative", "TN"),
            _case("no_rag", "hard_negative", "hard_negative", "FP"),
            _case("no_rag", "unrelated", "unrelated", "TN"),
        ]
    )

    assert summary["TP"] == 1
    assert summary["TN"] == 2
    assert summary["FP"] == 1
    assert summary["FN"] == 1
    assert summary["tpr"] == 0.5
    assert summary["tnr"] == 0.6667
    assert summary["hard_negative_reject_count"] == 1
    assert summary["hard_negative_reject_rate"] == 0.5


def test_acceptance_criteria_pass_and_fail_cases():
    gate_summary = {
        "TP": 18,
        "TN": 17,
        "FP": 3,
        "FN": 2,
        "tpr": 0.9,
        "tnr": 0.85,
        "hard_negative_reject_rate": 0.75,
        "hard_negative_reject_count": 9,
        "positive_by_category": {
            "food_safety": 1.0,
            "data_privacy": 0.75,
            "service_outage": 1.0,
            "product_quality": 1.0,
            "executive_misconduct": 1.0,
        },
    }
    end_to_end = {"recall_at_3": 0.63, "no_hit_accuracy": 0.85}

    acceptance = evaluate_acceptance(gate_summary, end_to_end)

    assert acceptance["criteria"] == ACCEPTANCE_CRITERIA
    assert acceptance["status"] == "PASS"
    assert all(acceptance["checks"].values())

    failing = evaluate_acceptance(
        {**gate_summary, "FN": 3, "tpr": 0.85},
        end_to_end,
    )
    assert failing["status"] == "FAIL"
    assert failing["checks"]["positive_tpr"] is False
    assert failing["checks"]["false_negative_count"] is False


def test_gate_fn_is_recorded_separately():
    case = {
        "id": "positive",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "service_outage",
        "event": "当前服务无法使用。",
        "notes": "positive",
    }

    result = evaluate_challenge_case(case, _FakeRetriever(), lambda **_: _gate_result(False))

    assert result["gate_label"] == "FN"
    assert result["failure_reason"] == "gate_false_negative"


def test_need_rag_false_does_not_call_retriever():
    case = {
        "id": "negative",
        "label": "no_rag",
        "type": "hard_negative",
        "category": "hard_negative",
        "event": "查询历史召回名单。",
        "notes": "lookup",
    }
    retriever = _CountingRetriever()

    result = evaluate_challenge_case(case, retriever, lambda **_: _gate_result(False))

    assert retriever.calls == 0
    assert result["retrieval"] == empty_retrieval_result()
    assert result["gate_label"] == "TN"


def test_bge_fallback_is_disabled():
    with pytest.raises(RuntimeError, match="Fallback is disabled"):
        DisabledFallbackRetriever().retrieve("query")


def test_run_challenge_evaluation_with_fake_retriever_does_not_modify_frozen_files():
    challenge_before = Path(CHALLENGE_PATH).read_bytes()
    protocol_before = Path(PROTOCOL_PATH).read_bytes()

    result = run_challenge_evaluation(
        retriever=_FakeRetriever(),
        gate_fn=lambda **_: _gate_result(True),
    )

    assert result["gate"]["TP"] == 20
    assert result["gate"]["FP"] == 20
    assert result["end_to_end"]["gate_failure_count"] == 20
    assert Path(CHALLENGE_PATH).read_bytes() == challenge_before
    assert Path(PROTOCOL_PATH).read_bytes() == protocol_before


def _case(label, case_type, category, gate_label):
    return {
        "label": label,
        "type": case_type,
        "category": category,
        "gate_label": gate_label,
        "weak_current_incident": label == "need_rag",
        "intent_type": "training_learning" if case_type == "hard_negative" else None,
    }


def _gate_result(need_rag):
    return {
        "need_rag": need_rag,
        "intent": "crisis_response_needed" if need_rag else "information_lookup",
        "decision_score": 1,
        "current_incident": need_rag,
        "current_incident_signals": ["current_response_need"] if need_rag else [],
        "task_intent": "ambiguous_enterprise_risk",
        "decision_path": "mock",
        "matched_signals": [],
        "negative_signals": [],
        "reason": "mock",
    }


class _FakeRetriever:
    def retrieve(self, query, top_k=5):
        return RetrievalResult(
            context="mock",
            chunks=[],
            sources=[
                {
                    "source": "data_privacy.md",
                    "score": 0.8,
                    "rerank_score": 0.3,
                    "retrieval_type": "hybrid",
                    "retrieval_fallback": False,
                }
            ],
        )


class _CountingRetriever(_FakeRetriever):
    def __init__(self):
        self.calls = 0

    def retrieve(self, query, top_k=5):
        self.calls += 1
        return super().retrieve(query, top_k)


def _count_by(items, field):
    counts = {}
    for item in items:
        value = item[field]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
