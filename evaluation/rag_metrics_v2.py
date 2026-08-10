K_VALUES = (1, 3, 5)

SOURCE_CATEGORIES = {
    "food_safety.md": "food_safety",
    "legal_risk_rules.md": "legal",
    "crisis_response.md": "crisis_response",
}


def evaluate_retrieval_case(case: dict, retrieval: dict, k_values: tuple[int, ...] = K_VALUES) -> dict:
    unique_sources = dedupe_sources([source.get("source", "") for source in retrieval.get("sources", [])])
    chunks = retrieval.get("chunks", [])
    expected_hit = bool(case.get("expected_hit", True))
    acceptable_sources = list(case.get("acceptable_sources", []))
    forbidden_sources = set(case.get("forbidden_sources", []))
    forbidden_categories = set(case.get("forbidden_categories", []))

    metrics = {}
    for k in k_values:
        metrics[f"recall_at_{k}"] = (
            calculate_recall_at_k(acceptable_sources, unique_sources, k)
            if expected_hit
            else None
        )
        metrics[f"precision_at_{k}"] = calculate_precision_at_k(
            acceptable_sources,
            unique_sources,
            k,
        )

    metrics["reciprocal_rank"] = (
        calculate_reciprocal_rank(acceptable_sources, unique_sources)
        if expected_hit
        else None
    )
    metrics["no_hit_correct"] = (len(unique_sources) == 0) if not expected_hit else None
    metrics["source_category_match"] = calculate_source_category_match(
        unique_sources,
        acceptable_sources,
    )
    metrics["context_pollution_rate"] = calculate_context_pollution_rate(
        unique_sources,
        forbidden_sources,
        forbidden_categories,
    )

    return {
        **metrics,
        "retrieved_sources": unique_sources,
        "source_count": len(unique_sources),
        "scores": _extract_values(retrieval.get("sources", []), "score"),
        "rerank_scores": _extract_values(retrieval.get("sources", []), "rerank_score"),
        "retrieval_type": _first_metadata_value(retrieval, "retrieval_type"),
        "fallback_used": bool(_first_metadata_value(retrieval, "retrieval_fallback")),
        "chunks": chunks,
        "failure_reason": classify_failure(case, unique_sources, chunks, metrics),
    }


def summarize_rag_results(case_results: list[dict], k_values: tuple[int, ...] = K_VALUES) -> dict:
    return {
        "overall": summarize_subset(case_results, k_values),
        "splits": _summarize_by_field(case_results, "split", k_values),
        "categories": _summarize_by_field(case_results, "category", k_values),
        "worst_cases": select_worst_cases(case_results, limit=5),
    }


def summarize_subset(case_results: list[dict], k_values: tuple[int, ...] = K_VALUES) -> dict:
    hit_cases = [case for case in case_results if case.get("expected_hit")]
    no_hit_cases = [case for case in case_results if not case.get("expected_hit")]

    summary = {
        "total_cases": len(case_results),
        "hit_case_count": len(hit_cases),
        "no_hit_case_count": len(no_hit_cases),
        "no_hit_accuracy": _average(
            [1.0 if case["metrics"].get("no_hit_correct") else 0.0 for case in no_hit_cases]
        ),
        "mrr": _average(
            [
                case["metrics"]["reciprocal_rank"]
                for case in hit_cases
                if case["metrics"].get("reciprocal_rank") is not None
            ]
        ),
        "source_category_match": _weighted_average(
            [
                (
                    case["metrics"]["source_category_match"],
                    max(1, case["metrics"]["source_count"]),
                )
                for case in case_results
            ]
        ),
        "context_pollution_rate": _weighted_average(
            [
                (
                    case["metrics"]["context_pollution_rate"],
                    max(1, case["metrics"]["source_count"]),
                )
                for case in case_results
            ]
        ),
        "fallback_count": sum(1 for case in case_results if case["metrics"].get("fallback_used")),
    }

    for k in k_values:
        summary[f"recall_at_{k}"] = _average(
            [
                case["metrics"][f"recall_at_{k}"]
                for case in hit_cases
                if case["metrics"].get(f"recall_at_{k}") is not None
            ]
        )
        summary[f"precision_at_{k}"] = _average(
            [case["metrics"][f"precision_at_{k}"] for case in case_results]
        )

    return summary


def calculate_recall_at_k(acceptable_sources: list[str], retrieved_sources: list[str], k: int) -> float:
    if not acceptable_sources:
        return 0.0
    top_sources = set(retrieved_sources[:k])
    hits = top_sources & set(acceptable_sources)
    return round(len(hits) / len(set(acceptable_sources)), 4)


def calculate_precision_at_k(acceptable_sources: list[str], retrieved_sources: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_sources = set(retrieved_sources[:k])
    hits = top_sources & set(acceptable_sources)
    return round(len(hits) / k, 4)


def calculate_reciprocal_rank(acceptable_sources: list[str], retrieved_sources: list[str]) -> float:
    expected = set(acceptable_sources)
    if not expected:
        return 0.0
    for index, source in enumerate(retrieved_sources, start=1):
        if source in expected:
            return round(1 / index, 4)
    return 0.0


def calculate_source_category_match(retrieved_sources: list[str], acceptable_sources: list[str]) -> float:
    if not retrieved_sources:
        return 1.0
    acceptable = set(acceptable_sources)
    matched = sum(1 for source in retrieved_sources if source in acceptable)
    return round(matched / len(retrieved_sources), 4)


def calculate_context_pollution_rate(
    retrieved_sources: list[str],
    forbidden_sources: set[str],
    forbidden_categories: set[str],
) -> float:
    if not retrieved_sources:
        return 0.0
    polluted = 0
    for source in retrieved_sources:
        category = SOURCE_CATEGORIES.get(source, "unknown")
        if source in forbidden_sources or category in forbidden_categories:
            polluted += 1
    return round(polluted / len(retrieved_sources), 4)


def dedupe_sources(sources: list[str]) -> list[str]:
    result = []
    for source in sources:
        if source and source not in result:
            result.append(source)
    return result


def classify_failure(case: dict, retrieved_sources: list[str], chunks: list[dict], metrics: dict) -> str:
    expected_hit = bool(case.get("expected_hit", True))
    acceptable_sources = set(case.get("acceptable_sources", []))

    if expected_hit and not retrieved_sources:
        if chunks:
            return "threshold_filtered"
        return "no_hit"
    if not expected_hit and retrieved_sources:
        return "unexpected_hit"
    if expected_hit and not (acceptable_sources & set(retrieved_sources)):
        return "wrong_category"
    if metrics.get("context_pollution_rate", 0.0) > 0:
        return "wrong_category"
    if expected_hit and metrics.get("reciprocal_rank") == 0:
        return "keyword_miss"
    return "none"


def select_worst_cases(case_results: list[dict], limit: int = 5) -> list[dict]:
    ranked = sorted(case_results, key=_case_badness_score, reverse=True)
    return [
        {
            "case_id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "acceptable_sources": case.get("acceptable_sources", []),
            "actual_sources": case["metrics"]["retrieved_sources"],
            "scores": case["metrics"]["scores"],
            "rerank_scores": case["metrics"]["rerank_scores"],
            "retrieval_type": case["metrics"]["retrieval_type"],
            "fallback_used": case["metrics"]["fallback_used"],
            "failure_reason": case["metrics"]["failure_reason"],
        }
        for case in ranked[:limit]
    ]


def _case_badness_score(case: dict) -> float:
    metrics = case["metrics"]
    score = 0.0
    if case.get("expected_hit"):
        score += 1 - (metrics.get("recall_at_5") or 0)
        score += 1 - (metrics.get("reciprocal_rank") or 0)
    else:
        score += 0 if metrics.get("no_hit_correct") else 2
    score += metrics.get("context_pollution_rate", 0)
    if metrics.get("fallback_used"):
        score += 0.5
    return score


def _summarize_by_field(case_results: list[dict], field: str, k_values: tuple[int, ...]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for case in case_results:
        grouped.setdefault(str(case.get(field, "unknown")), []).append(case)
    return {
        name: summarize_subset(items, k_values)
        for name, items in sorted(grouped.items())
    }


def _extract_values(sources: list[dict], field: str) -> list[float | None]:
    return [source.get(field) for source in sources]


def _first_metadata_value(retrieval: dict, field: str):
    sources = retrieval.get("sources", [])
    if sources:
        return sources[0].get(field)
    chunks = retrieval.get("chunks", [])
    if chunks:
        metadata = chunks[0].get("metadata", {})
        return metadata.get(field)
    return None


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _weighted_average(values: list[tuple[float, int]]) -> float:
    total_weight = sum(weight for _, weight in values)
    if not total_weight:
        return 0.0
    return round(sum(value * weight for value, weight in values) / total_weight, 4)
