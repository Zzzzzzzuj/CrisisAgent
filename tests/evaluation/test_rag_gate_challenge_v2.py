import json
from pathlib import Path

import pytest

from backend.rag.schemas import RetrievalResult
from evaluation.rag_gate_challenge_v2_evaluator import (
    ACCEPTANCE_CRITERIA,
    CHALLENGE_PATH,
    PROTOCOL_PATH,
    DisabledFallbackRetriever,
    empty_retrieval_result,
    evaluate_acceptance,
    evaluate_challenge_case,
    load_challenge_cases,
    normalize_case_for_retrieval,
    run_challenge_evaluation,
    summarize_gate_results,
)


def test_challenge_v2_dataset_shape_is_frozen():
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


def test_challenge_v2_case_ids_are_unique():
    cases = load_challenge_cases()
    ids = [case["id"] for case in cases]

    assert len(ids) == len(set(ids))


def test_hard_negative_intent_type_coverage_is_recorded():
    cases = load_challenge_cases()
    hard_negatives = [case for case in cases if case["type"] == "hard_negative"]
    intent_types = {case["intent_type"] for case in hard_negatives}

    assert len(hard_negatives) == 12
    assert {
        "historical_analysis",
        "statistics_or_reporting",
        "preparedness_drill",
        "future_hypothetical",
        "policy_learning",
        "content_editing",
        "lookup",
        "customer_service",
        "template_writing",
        "trend_analysis",
    } <= intent_types


def test_evaluator_passes_only_event_to_gate():
    case = {
        "id": "case_1",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "data_privacy",
        "event": "用户发现其他账号信息短暂出现在自己的页面中。",
        "notes": "evaluation only",
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


def test_tp_tn_fp_fn_summary_is_correct():
    summary = summarize_gate_results(
        [
            {"label": "need_rag", "type": "positive_crisis", "category": "food_safety", "gate_label": "TP"},
            {"label": "need_rag", "type": "positive_crisis", "category": "food_safety", "gate_label": "FN"},
            {"label": "no_rag", "type": "hard_negative", "category": "hard_negative", "gate_label": "TN"},
            {"label": "no_rag", "type": "hard_negative", "category": "hard_negative", "gate_label": "FP"},
        ]
    )

    assert summary["TP"] == 1
    assert summary["TN"] == 1
    assert summary["FP"] == 1
    assert summary["FN"] == 1
    assert summary["tpr"] == 0.5
    assert summary["tnr"] == 0.5
    assert summary["hard_negative_reject_count"] == 1
    assert summary["hard_negative_reject_rate"] == 0.5


def test_category_breakdown_and_hard_negative_acceptance_criteria():
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


def test_acceptance_fails_when_fn_count_or_category_tpr_fails():
    gate_summary = {
        "TP": 17,
        "TN": 20,
        "FP": 0,
        "FN": 3,
        "tpr": 0.85,
        "tnr": 1.0,
        "hard_negative_reject_rate": 1.0,
        "hard_negative_reject_count": 12,
        "positive_by_category": {
            "food_safety": 1.0,
            "data_privacy": 0.5,
            "service_outage": 1.0,
            "product_quality": 1.0,
            "executive_misconduct": 1.0,
        },
    }
    end_to_end = {"recall_at_3": 0.7, "no_hit_accuracy": 1.0}

    acceptance = evaluate_acceptance(gate_summary, end_to_end)

    assert acceptance["status"] == "FAIL"
    assert acceptance["checks"]["false_negative_count"] is False
    assert acceptance["checks"]["positive_category_tpr"] is False


def test_need_rag_false_does_not_call_retriever():
    case = {
        "id": "case_1",
        "label": "no_rag",
        "type": "hard_negative",
        "category": "hard_negative",
        "event": "请查询历史召回名单。",
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


def test_normalized_positive_and_negative_cases_keep_gold_out_of_gate_input():
    positive = {
        "id": "pos",
        "label": "need_rag",
        "type": "positive_crisis",
        "category": "service_outage",
        "event": "服务无法使用。",
        "notes": "gold",
    }
    negative = {
        "id": "neg",
        "label": "no_rag",
        "type": "unrelated",
        "category": "unrelated",
        "event": "骑行路线。",
        "notes": "gold",
    }

    assert normalize_case_for_retrieval(positive)["acceptable_sources"] == ["service_outage.md"]
    assert normalize_case_for_retrieval(negative)["acceptable_sources"] == []


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
        return super().retrieve(query, top_k=top_k)


def _gate_result(need_rag):
    return {
        "need_rag": need_rag,
        "intent": "crisis_response_needed" if need_rag else "information_lookup",
        "decision_score": 1 if need_rag else -1,
        "matched_signals": ["mock"] if need_rag else [],
        "negative_signals": [] if need_rag else ["mock_negative"],
        "reason": "mock",
    }


def _count_by(cases, field):
    counts = {}
    for case in cases:
        counts[case[field]] = counts.get(case[field], 0) + 1
    return dict(sorted(counts.items()))
