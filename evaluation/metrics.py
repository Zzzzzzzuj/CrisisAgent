from datetime import datetime


def calculate_accuracy(case_results: list[dict], match_field: str) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    hits = sum(1 for item in case_results if item.get(match_field))
    return round(hits / total_cases, 4)


def calculate_fallback_rate(case_results: list[dict]) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    fallback_cases = sum(1 for item in case_results if item.get("fallback"))
    return round(fallback_cases / total_cases, 4)


def calculate_average_duration_ms(case_results: list[dict]) -> float:
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    total_duration = sum(item.get("trace_duration_ms", 0) for item in case_results)
    return round(total_duration / total_cases, 2)


def calculate_rag_hit_rate(case_results: list[dict]) -> float:
    rag_cases = [item for item in case_results if item.get("rag_enabled")]
    if not rag_cases:
        return 0.0

    hits = sum(1 for item in rag_cases if item.get("rag_hit"))
    return round(hits / len(rag_cases), 4)


def calculate_average_retrieved_sources(case_results: list[dict]) -> float:
    rag_cases = [item for item in case_results if item.get("rag_enabled")]
    if not rag_cases:
        return 0.0

    total_sources = sum(item.get("rag_source_count", 0) for item in rag_cases)
    return round(total_sources / len(rag_cases), 2)


def calculate_source_distribution(case_results: list[dict]) -> dict:
    distribution: dict[str, int] = {}
    for item in case_results:
        for source in item.get("rag_sources", []):
            distribution[source] = distribution.get(source, 0) + 1
    return dict(sorted(distribution.items()))


def calculate_recall_at_k(case_results: list[dict]) -> float:
    scored_cases = [item for item in case_results if item.get("expected_sources")]
    if not scored_cases:
        return 0.0

    total_recall = 0.0
    for item in scored_cases:
        expected_sources = set(item.get("expected_sources", []))
        retrieved_sources = set(item.get("rag_sources", []))
        hits = expected_sources & retrieved_sources
        total_recall += len(hits) / len(expected_sources)

    return round(total_recall / len(scored_cases), 4)


def calculate_mrr(case_results: list[dict]) -> float:
    scored_cases = [item for item in case_results if item.get("expected_sources")]
    if not scored_cases:
        return 0.0

    total_rr = 0.0
    for item in scored_cases:
        expected_sources = set(item.get("expected_sources", []))
        reciprocal_rank = 0.0
        for index, source in enumerate(item.get("rag_sources", []), start=1):
            if source in expected_sources:
                reciprocal_rank = 1 / index
                break
        total_rr += reciprocal_rank

    return round(total_rr / len(scored_cases), 4)


def calculate_average_rerank_gain(case_results: list[dict]) -> float:
    gains = [
        item["rerank_gain"]
        for item in case_results
        if isinstance(item.get("rerank_gain"), int | float)
    ]
    if not gains:
        return 0.0
    return round(sum(gains) / len(gains), 2)


def calculate_rerank_rank_change(expected_sources: list[str], chunks: list[dict]) -> dict:
    if not expected_sources or not chunks:
        return {
            "before_rank": None,
            "after_rank": None,
            "rerank_gain": 0,
        }

    score_ranked = sorted(
        chunks,
        key=lambda chunk: chunk.get("score") if chunk.get("score") is not None else -1,
        reverse=True,
    )
    rerank_score_ranked = sorted(
        chunks,
        key=lambda chunk: chunk.get("rerank_score") if chunk.get("rerank_score") is not None else -1,
        reverse=True,
    )

    before_rank = _find_first_expected_source_rank(expected_sources, score_ranked)
    after_rank = _find_first_expected_source_rank(expected_sources, rerank_score_ranked)
    if before_rank is None or after_rank is None:
        return {
            "before_rank": before_rank,
            "after_rank": after_rank,
            "rerank_gain": 0,
        }

    return {
        "before_rank": before_rank,
        "after_rank": after_rank,
        "rerank_gain": before_rank - after_rank,
    }


def _find_first_expected_source_rank(expected_sources: list[str], chunks: list[dict]) -> int | None:
    expected = set(expected_sources)
    for index, chunk in enumerate(chunks, start=1):
        if chunk.get("source") in expected:
            return index
    return None


def calculate_trace_duration_ms(agent_trace: list[dict]) -> int:
    if not agent_trace:
        return 0

    start_time = datetime.fromisoformat(agent_trace[0]["start_time"])
    end_time = datetime.fromisoformat(agent_trace[-1]["end_time"])
    return int((end_time - start_time).total_seconds() * 1000)


def calculate_agent_duration_ms(trace_item: dict) -> int:
    start_time = datetime.fromisoformat(trace_item["start_time"])
    end_time = datetime.fromisoformat(trace_item["end_time"])
    return int((end_time - start_time).total_seconds() * 1000)


def summarize_agent_metrics(case_results: list[dict]) -> dict:
    per_agent: dict[str, dict] = {}

    for case_result in case_results:
        for item in case_result.get("trace", []):
            agent_key = item["agent"]
            metrics = per_agent.setdefault(
                agent_key,
                {
                    "agent": item["agent"],
                    "name": item["name"],
                    "total_runs": 0,
                    "total_duration_ms": 0,
                    "fallback_count": 0,
                },
            )
            metrics["total_runs"] += 1
            metrics["total_duration_ms"] += calculate_agent_duration_ms(item)
            if item.get("fallback"):
                metrics["fallback_count"] += 1

    summary = {}
    for agent_key, metrics in per_agent.items():
        total_runs = metrics["total_runs"]
        average_duration_ms = metrics["total_duration_ms"] / total_runs if total_runs else 0.0
        fallback_rate = metrics["fallback_count"] / total_runs if total_runs else 0.0
        summary[agent_key] = {
            "agent": metrics["agent"],
            "name": metrics["name"],
            "average_duration_ms": round(average_duration_ms, 2),
            "fallback_count": metrics["fallback_count"],
            "fallback_rate": round(fallback_rate, 4),
            "total_runs": total_runs,
        }

    return summary


def summarize_category_metrics(case_results: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for item in case_results:
        category = item.get("category", "unknown")
        grouped.setdefault(category, []).append(item)

    summary = {}
    for category, items in grouped.items():
        summary[category] = {
            "total_cases": len(items),
            "risk_accuracy": calculate_accuracy(items, "risk_match"),
            "emotion_accuracy": calculate_accuracy(items, "emotion_match"),
            "tone_accuracy": calculate_accuracy(items, "tone_match"),
            "fallback_rate": calculate_fallback_rate(items),
            "average_duration_ms": calculate_average_duration_ms(items),
            "rag_hit_rate": calculate_rag_hit_rate(items),
            "average_retrieved_sources": calculate_average_retrieved_sources(items),
            "recall_at_k": calculate_recall_at_k(items),
            "mrr": calculate_mrr(items),
            "average_rerank_gain": calculate_average_rerank_gain(items),
        }

    return summary
