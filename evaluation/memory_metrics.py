def calculate_memory_hit_rate(case_results: list[dict]) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    hits = sum(1 for item in case_results if item.get("memory_hit"))
    return round(hits / total_cases, 4)


def calculate_memory_recall_at_k(case_results: list[dict]) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    hits = 0
    for item in case_results:
        expected_category = item.get("expected_category")
        retrieved_categories = item.get("retrieved_categories", [])
        if expected_category in retrieved_categories:
            hits += 1

    return round(hits / total_cases, 4)


def calculate_category_accuracy(case_results: list[dict]) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    hits = 0
    for item in case_results:
        retrieved_categories = item.get("retrieved_categories", [])
        predicted_category = retrieved_categories[0] if retrieved_categories else None
        if predicted_category == item.get("expected_category"):
            hits += 1

    return round(hits / total_cases, 4)


def calculate_memory_source_distribution(case_results: list[dict]) -> dict:
    distribution: dict[str, int] = {}
    for item in case_results:
        for category in item.get("retrieved_categories", []):
            distribution[category] = distribution.get(category, 0) + 1
    return dict(sorted(distribution.items()))


def evaluate_memory_case_result(case: dict, retrieved_memories: list[dict]) -> dict:
    retrieved_categories = [
        memory.get("category")
        for memory in retrieved_memories
        if memory.get("category")
    ]
    expected_category = case.get("expected_category")

    return {
        "event": case.get("event", ""),
        "expected_category": expected_category,
        "retrieved_categories": retrieved_categories,
        "retrieved_memory_ids": [
            memory.get("memory_id")
            for memory in retrieved_memories
            if memory.get("memory_id")
        ],
        "memory_hit": expected_category in retrieved_categories,
    }


def summarize_memory_results(case_results: list[dict]) -> dict:
    return {
        "total_cases": len(case_results),
        "memory_hit_rate": calculate_memory_hit_rate(case_results),
        "memory_recall_at_k": calculate_memory_recall_at_k(case_results),
        "category_accuracy": calculate_category_accuracy(case_results),
        "memory_source_distribution": calculate_memory_source_distribution(case_results),
        "case_results": case_results,
    }
