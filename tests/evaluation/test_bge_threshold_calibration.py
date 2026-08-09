from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.schemas import RetrievalResult
from evaluation.bge_threshold_calibration import (
    DEFAULT_PRODUCTION_THRESHOLD,
    collect_score_distribution,
    false_positive_count,
    load_negative_cases,
    no_hit_accuracy,
    summarize_negative_results,
    validate_negative_cases,
)


def _negative_case(case_id, case_type, sources):
    return {
        "id": case_id,
        "type": case_type,
        "expected_hit": False,
        "metrics": {
            "no_hit_correct": len(sources) == 0,
            "retrieved_sources": sources,
            "source_count": len(sources),
        },
    }


def test_negative_calibration_dataset_has_24_cases_and_three_types():
    cases = load_negative_cases()

    validate_negative_cases(cases)

    assert len(cases) == 24
    assert sum(1 for case in cases if case["type"] == "unrelated") == 8
    assert sum(1 for case in cases if case["type"] == "business_non_crisis") == 8
    assert sum(1 for case in cases if case["type"] == "hard_negative") == 8


def test_negative_calibration_cases_all_expect_no_hit():
    cases = load_negative_cases()

    assert all(case["expected_hit"] is False for case in cases)


def test_false_positive_count_and_no_hit_accuracy():
    cases = [
        _negative_case("a", "unrelated", []),
        _negative_case("b", "unrelated", ["service_outage.md"]),
        _negative_case("c", "hard_negative", []),
    ]

    assert false_positive_count(cases) == 1
    assert no_hit_accuracy(cases) == 0.6667


def test_negative_summary_reports_each_type_separately():
    cases = [
        _negative_case("u1", "unrelated", []),
        _negative_case("b1", "business_non_crisis", ["crisis_response.md"]),
        _negative_case("h1", "hard_negative", []),
    ]

    summary = summarize_negative_results(cases)

    assert summary["case_count"] == 3
    assert summary["false_positive_count"] == 1
    assert summary["type_metrics"]["unrelated"]["no_hit_accuracy"] == 1.0
    assert summary["type_metrics"]["business_non_crisis"]["no_hit_accuracy"] == 0.0
    assert summary["type_metrics"]["hard_negative"]["no_hit_accuracy"] == 1.0


def test_unrelated_cases_do_not_enter_positive_recall_denominator():
    cases = [
        _negative_case("u1", "unrelated", []),
        _negative_case("u2", "unrelated", ["service_outage.md"]),
    ]

    summary = summarize_negative_results(cases)

    assert "recall_at_3" not in summary
    assert summary["no_hit_accuracy"] == 0.5


def test_higher_threshold_cannot_increase_false_positive_results():
    low_threshold_results = [
        _negative_case("u1", "unrelated", ["service_outage.md"]),
        _negative_case("u2", "unrelated", ["crisis_response.md"]),
    ]
    high_threshold_results = [
        _negative_case("u1", "unrelated", []),
        _negative_case("u2", "unrelated", ["crisis_response.md"]),
    ]

    assert false_positive_count(high_threshold_results) <= false_positive_count(low_threshold_results)
    assert no_hit_accuracy(high_threshold_results) >= no_hit_accuracy(low_threshold_results)


def test_production_default_threshold_is_not_modified():
    retriever = RagPipelineRetriever()

    assert DEFAULT_PRODUCTION_THRESHOLD == 0.1
    assert retriever.min_rerank_score == 0.1


def test_score_distribution_keeps_vector_and_final_result_layers_separate():
    case = {
        "id": "case_1",
        "type": "hard_negative",
        "query": "监管政策讨论",
        "expected_hit": False,
    }
    pipeline = _FakeRetriever(
        RetrievalResult(
            context="",
            chunks=[],
            sources=[
                {
                    "source": "food_safety.md",
                    "score": 0.31,
                    "rerank_score": 0.22,
                }
            ],
        )
    )
    vector_retriever = _FakeRetriever(
        RetrievalResult(
            context="",
            chunks=[],
            sources=[
                {"source": "legal_risk_rules.md", "score": 0.82},
                {"source": "food_safety.md", "score": 0.74},
            ],
        )
    )

    distribution = collect_score_distribution([case], pipeline, vector_retriever)

    assert distribution[0]["vector_top_sources"] == ["legal_risk_rules.md", "food_safety.md"]
    assert distribution[0]["vector_scores"] == [0.82, 0.74]
    assert distribution[0]["hybrid_scores"] == [0.31]
    assert distribution[0]["top1_rerank_score"] == 0.22
    assert distribution[0]["final_categories"] == ["food_safety"]


class _FakeRetriever:
    def __init__(self, result):
        self.result = result

    def retrieve(self, query, top_k=5):
        return self.result
