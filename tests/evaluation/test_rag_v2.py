from evaluation.rag_evaluator_v2 import load_cases
from evaluation.rag_metrics_v2 import (
    calculate_context_pollution_rate,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    calculate_source_category_match,
    dedupe_sources,
    evaluate_retrieval_case,
    summarize_rag_results,
)


def test_recall_at_k_uses_unique_source_documents():
    retrieved_sources = dedupe_sources(["food_safety.md", "food_safety.md", "crisis_response.md"])

    assert retrieved_sources == ["food_safety.md", "crisis_response.md"]
    assert calculate_recall_at_k(["food_safety.md", "legal_risk_rules.md"], retrieved_sources, 1) == 0.5
    assert calculate_recall_at_k(["food_safety.md", "legal_risk_rules.md"], retrieved_sources, 3) == 0.5


def test_precision_at_k_uses_source_document_level():
    retrieved_sources = ["food_safety.md", "crisis_response.md", "legal_risk_rules.md"]

    assert calculate_precision_at_k(["food_safety.md"], retrieved_sources, 1) == 1.0
    assert calculate_precision_at_k(["food_safety.md"], retrieved_sources, 3) == 0.3333


def test_mrr_uses_first_acceptable_source_rank():
    retrieved_sources = ["crisis_response.md", "legal_risk_rules.md", "food_safety.md"]

    assert calculate_reciprocal_rank(["food_safety.md"], retrieved_sources) == 0.3333
    assert calculate_reciprocal_rank(["unknown.md"], retrieved_sources) == 0.0


def test_no_hit_accuracy_is_separate_from_recall_denominator():
    cases = [
        _result_case("hit-1", True, ["food_safety.md"], ["food_safety.md"]),
        _result_case("nohit-1", False, [], []),
        _result_case("nohit-2", False, [], ["crisis_response.md"]),
    ]

    summary = summarize_rag_results(cases)["overall"]

    assert summary["hit_case_count"] == 1
    assert summary["no_hit_case_count"] == 2
    assert summary["recall_at_1"] == 1.0
    assert summary["mrr"] == 1.0
    assert summary["no_hit_accuracy"] == 0.5


def test_source_category_match_counts_acceptable_sources():
    assert calculate_source_category_match(["food_safety.md", "crisis_response.md"], ["food_safety.md"]) == 0.5
    assert calculate_source_category_match([], ["food_safety.md"]) == 1.0


def test_context_pollution_rate_uses_forbidden_sources_and_categories():
    rate = calculate_context_pollution_rate(
        ["food_safety.md", "crisis_response.md", "legal_risk_rules.md"],
        forbidden_sources={"food_safety.md"},
        forbidden_categories={"legal"},
    )

    assert rate == 0.6667


def test_empty_retrieval_result_is_handled():
    case = {
        "id": "case",
        "expected_hit": True,
        "acceptable_sources": ["food_safety.md"],
        "forbidden_sources": [],
        "forbidden_categories": [],
    }
    retrieval = {"sources": [], "chunks": [], "context": ""}

    result = evaluate_retrieval_case(case, retrieval)

    assert result["retrieved_sources"] == []
    assert result["recall_at_1"] == 0.0
    assert result["reciprocal_rank"] == 0.0
    assert result["failure_reason"] == "no_hit"


def test_same_source_multiple_chunks_count_once():
    case = {
        "id": "case",
        "expected_hit": True,
        "acceptable_sources": ["food_safety.md"],
        "forbidden_sources": [],
        "forbidden_categories": [],
    }
    retrieval = {
        "sources": [
            {"source": "food_safety.md", "score": 0.9, "rerank_score": 0.8},
            {"source": "food_safety.md", "score": 0.7, "rerank_score": 0.6},
        ],
        "chunks": [],
        "context": "",
    }

    result = evaluate_retrieval_case(case, retrieval)

    assert result["retrieved_sources"] == ["food_safety.md"]
    assert result["recall_at_1"] == 1.0
    assert result["precision_at_1"] == 1.0


def test_development_and_final_are_summarized_separately():
    cases = [
        _result_case("dev", True, ["food_safety.md"], ["food_safety.md"], split="development"),
        _result_case("final", True, ["food_safety.md"], [], split="final"),
    ]

    summary = summarize_rag_results(cases)

    assert summary["splits"]["development"]["recall_at_1"] == 1.0
    assert summary["splits"]["final"]["recall_at_1"] == 0.0


def test_rag_cases_v2_dataset_shape():
    cases = load_cases()
    split_counts = {}
    category_counts = {}
    ids = [case["id"] for case in cases]
    for case in cases:
        split_counts[case["split"]] = split_counts.get(case["split"], 0) + 1
        category_counts[case["category"]] = category_counts.get(case["category"], 0) + 1

    assert len(cases) == 30
    assert split_counts == {"development": 18, "final": 12}
    assert set(category_counts.values()) == {5}
    assert len(category_counts) == 6
    assert len(ids) == len(set(ids))
    assert any(case["expected_hit"] is False for case in cases)


def _result_case(
    case_id: str,
    expected_hit: bool,
    acceptable_sources: list[str],
    retrieved_sources: list[str],
    split: str = "development",
    category: str = "food_safety",
) -> dict:
    retrieval = {
        "sources": [{"source": source, "score": 1.0, "rerank_score": 1.0} for source in retrieved_sources],
        "chunks": [],
        "context": "",
    }
    case = {
        "id": case_id,
        "split": split,
        "category": category,
        "query": case_id,
        "expected_hit": expected_hit,
        "acceptable_sources": acceptable_sources,
        "forbidden_sources": [],
        "forbidden_categories": [],
    }
    return {
        **case,
        "metrics": evaluate_retrieval_case(case, retrieval),
    }
