from evaluation.memory_metrics import (
    calculate_category_accuracy,
    calculate_memory_hit_rate,
    calculate_memory_recall_at_k,
    calculate_memory_source_distribution,
    evaluate_memory_case_result,
    summarize_memory_results,
)


def test_memory_hit_rate():
    case_results = [
        {"memory_hit": True},
        {"memory_hit": False},
        {"memory_hit": True},
    ]

    assert calculate_memory_hit_rate(case_results) == 0.6667


def test_memory_recall_at_k():
    case_results = [
        {
            "expected_category": "food_safety",
            "retrieved_categories": ["food_safety", "crisis_response"],
        },
        {
            "expected_category": "data_security",
            "retrieved_categories": ["food_safety", "crisis_response"],
        },
    ]

    assert calculate_memory_recall_at_k(case_results) == 0.5


def test_category_accuracy():
    case_results = [
        {
            "expected_category": "food_safety",
            "retrieved_categories": ["food_safety", "crisis_response"],
        },
        {
            "expected_category": "data_security",
            "retrieved_categories": ["crisis_response", "data_security"],
        },
    ]

    assert calculate_category_accuracy(case_results) == 0.5


def test_memory_source_distribution():
    case_results = [
        {"retrieved_categories": ["food_safety", "data_security"]},
        {"retrieved_categories": ["food_safety"]},
    ]

    assert calculate_memory_source_distribution(case_results) == {
        "data_security": 1,
        "food_safety": 2,
    }


def test_evaluate_memory_case_result_and_summary():
    case = {
        "event": "食品企业使用过期原料",
        "expected_category": "food_safety",
    }
    retrieved_memories = [
        {"memory_id": "memory-1", "category": "food_safety"},
        {"memory_id": "memory-2", "category": "data_security"},
    ]

    case_result = evaluate_memory_case_result(case, retrieved_memories)
    summary = summarize_memory_results([case_result])

    assert case_result["memory_hit"] is True
    assert case_result["retrieved_memory_ids"] == ["memory-1", "memory-2"]
    assert summary["memory_hit_rate"] == 1.0
    assert summary["memory_recall_at_k"] == 1.0
    assert summary["category_accuracy"] == 1.0
