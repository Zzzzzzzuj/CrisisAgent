def calculate_case_metrics(expected_sources: list[str], retrieved_sources: list[str]) -> dict:
    target_rank = find_first_target_rank(expected_sources, retrieved_sources)
    return {
        "recall_at_k": calculate_case_recall_at_k(expected_sources, retrieved_sources),
        "reciprocal_rank": round(1 / target_rank, 4) if target_rank else 0.0,
        "target_rank": target_rank,
    }


def calculate_case_recall_at_k(expected_sources: list[str], retrieved_sources: list[str]) -> float:
    if not expected_sources:
        return 0.0

    hits = set(expected_sources) & set(retrieved_sources)
    return round(len(hits) / len(expected_sources), 4)


def find_first_target_rank(expected_sources: list[str], retrieved_sources: list[str]) -> int | None:
    expected = set(expected_sources)
    for index, source in enumerate(retrieved_sources, start=1):
        if source in expected:
            return index
    return None


def summarize_embedding_results(case_results: list[dict]) -> dict:
    if not case_results:
        return {
            "total_cases": 0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "average_target_rank": 0.0,
        }

    target_ranks = [
        item["target_rank"]
        for item in case_results
        if item.get("target_rank") is not None
    ]
    return {
        "total_cases": len(case_results),
        "recall_at_k": round(
            sum(item["recall_at_k"] for item in case_results) / len(case_results),
            4,
        ),
        "mrr": round(
            sum(item["reciprocal_rank"] for item in case_results) / len(case_results),
            4,
        ),
        "average_target_rank": round(sum(target_ranks) / len(target_ranks), 2)
        if target_ranks
        else 0.0,
    }
