from backend.rag.schemas import RetrievalResult
from evaluation.rag_gate_evaluator_v2 import (
    empty_retrieval_result,
    evaluate_case_with_gate,
    run_gate_evaluation,
    summarize_gate_results,
)


def _positive_case(case_id="positive_1", query="某APP被曝泄露用户身份证信息，用户要求平台回应"):
    return {
        "id": case_id,
        "split": "development",
        "category": "data_privacy",
        "query": query,
        "expected_hit": True,
        "acceptable_sources": ["data_privacy.md"],
        "forbidden_sources": [],
        "forbidden_categories": [],
    }


def _negative_case(case_id="negative_1", case_type="hard_negative", query="用户想查询隐私政策入口在哪里"):
    return {
        "id": case_id,
        "split": "development",
        "category": case_type,
        "type": case_type,
        "query": query,
        "expected_hit": False,
        "acceptable_sources": [],
        "forbidden_sources": [],
        "forbidden_categories": [],
    }


def test_gate_false_returns_empty_retrieval_and_does_not_call_retriever():
    retriever = _CountingRetriever()

    result = evaluate_case_with_gate(_negative_case(), retriever)

    assert retriever.calls == 0
    assert result["retrieval"] == empty_retrieval_result()
    assert result["gate_label"] == "TN"


def test_gate_true_calls_retriever():
    retriever = _CountingRetriever()

    result = evaluate_case_with_gate(_positive_case(), retriever)

    assert retriever.calls == 1
    assert result["gate_label"] == "TP"
    assert result["metrics"]["retrieved_sources"] == ["data_privacy.md"]


def test_gate_summary_reports_confusion_matrix_and_rates():
    cases = [
        {"expected_hit": True, "gate_label": "TP"},
        {"expected_hit": True, "gate_label": "FN"},
        {"expected_hit": False, "type": "hard_negative", "gate_label": "TN"},
        {"expected_hit": False, "type": "hard_negative", "gate_label": "FP"},
    ]

    summary = summarize_gate_results(cases)

    assert summary["TP"] == 1
    assert summary["TN"] == 1
    assert summary["FP"] == 1
    assert summary["FN"] == 1
    assert summary["tpr"] == 0.5
    assert summary["tnr"] == 0.5
    assert summary["hard_negative_reject_rate"] == 0.5


def test_run_gate_evaluation_with_fake_retriever_keeps_false_negatives_visible(tmp_path):
    positive_path = tmp_path / "positive_cases.json"
    negative_path = tmp_path / "negative_cases.json"
    positive_path.write_text(
        """
[
  {
    "id": "pos_1",
    "split": "development",
    "category": "data_privacy",
    "query": "某APP被曝泄露用户身份证信息，用户要求平台回应",
    "expected_hit": true,
    "acceptable_sources": ["data_privacy.md"],
    "forbidden_sources": [],
    "forbidden_categories": []
  },
  {
    "id": "pos_2",
    "split": "development",
    "category": "data_privacy",
    "query": "个人信息安全 隐私保护 平台说明",
    "expected_hit": true,
    "acceptable_sources": ["data_privacy.md"],
    "forbidden_sources": [],
    "forbidden_categories": []
  }
]
""".strip(),
        encoding="utf-8",
    )
    negative_path.write_text(
        """
[
  {
    "id": "neg_1",
    "type": "hard_negative",
    "query": "用户想查询隐私政策入口在哪里",
    "expected_hit": false
  }
]
""".strip(),
        encoding="utf-8",
    )

    result = run_gate_evaluation(positive_path, negative_path, retriever=_CountingRetriever())

    assert result["gate"]["FN"] == 1
    assert result["false_negatives"][0]["case_id"] == "pos_2"
    assert result["gate"]["hard_negative_reject_rate"] == 1.0
    assert result["with_gate"]["no_hit_accuracy"] == 1.0


class _CountingRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve(self, query, top_k=5):
        self.calls += 1
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
