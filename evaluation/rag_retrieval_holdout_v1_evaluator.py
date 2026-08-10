import copy
import json
import subprocess
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import _merge_rewritten_chunks
from backend.rag.query_rewriter import rewrite_query
from backend.rag.reranker import RuleBasedReranker
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.rag.vector_retriever import VectorRetriever
from evaluation.reranker_v2_development import (
    BASELINE_FORMULA,
    BGE_MODEL_NAME,
    MIN_RERANK_SCORE,
    TOP_K,
    _baseline_rerank_chunk,
    _format_context,
    _source_dict,
)


HOLDOUT_PATH = PROJECT_ROOT / "evaluation" / "rag_retrieval_holdout_v1.json"
PROTOCOL_PATH = PROJECT_ROOT / "evaluation" / "reports" / "rag_retrieval_holdout_v1_protocol.md"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_rag_retrieval_holdout_v1.md"
RERANKER_V2_FROZEN_COMMIT = "22fed48"


class DisabledFallbackRetriever:
    def retrieve(self, query: str, top_k: int = TOP_K) -> RetrievalResult:
        raise RuntimeError("Fallback is disabled for Retrieval Holdout v1.")


class FrozenOldRuleBasedReranker:
    formula = BASELINE_FORMULA

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = TOP_K,
    ) -> RetrievalResult:
        if top_k <= 0 or not chunks:
            return RetrievalResult(context="", chunks=[], sources=[])

        reranked_chunks = [_baseline_rerank_chunk(query, chunk) for chunk in chunks]
        reranked_chunks.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
        top_chunks = reranked_chunks[:top_k]
        return RetrievalResult(
            context=_format_context(top_chunks),
            chunks=top_chunks,
            sources=[_source_dict(chunk) for chunk in top_chunks],
        )


def load_holdout_cases(path: str | Path = HOLDOUT_PATH, validate: bool = True) -> list[dict]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if validate:
        validate_holdout_cases(cases)
    return cases


def validate_holdout_cases(cases: list[dict]) -> None:
    if len(cases) != 30:
        raise ValueError(f"Retrieval Holdout v1 must contain 30 cases, got {len(cases)}.")
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Retrieval Holdout v1 contains duplicate case_id values.")

    category_counts = Counter(case.get("category") for case in cases)
    expected_counts = {
        "food_safety": 6,
        "data_privacy": 6,
        "service_outage": 6,
        "product_quality": 6,
        "executive_misconduct": 6,
    }
    if dict(sorted(category_counts.items())) != expected_counts:
        raise ValueError(f"Unexpected category distribution: {dict(category_counts)}.")

    required_fields = {
        "case_id",
        "category",
        "event",
        "expected_retrieval",
        "acceptable_sources",
        "neutral_sources",
        "forbidden_sources",
    }
    for case in cases:
        missing = required_fields - set(case)
        if missing:
            raise ValueError(f"Case {case.get('case_id')} missing fields: {sorted(missing)}.")
        if case.get("expected_retrieval") is not True:
            raise ValueError(f"Case {case.get('case_id')} must set expected_retrieval=true.")
        _validate_source_groups(case)


def run_holdout_evaluation(
    holdout_path: str | Path = HOLDOUT_PATH,
    hybrid_retriever=None,
    old_reranker=None,
    v2_reranker=None,
    validate: bool = True,
) -> dict:
    cases = load_holdout_cases(holdout_path, validate=validate)
    active_hybrid = hybrid_retriever or build_bge_hybrid_retriever()
    old = old_reranker or FrozenOldRuleBasedReranker()
    v2 = v2_reranker or RuleBasedReranker()

    case_results = [
        evaluate_holdout_case(case, active_hybrid, old, v2)
        for case in cases
    ]
    candidate_pool_parity = all(case["candidate_pool_parity"] for case in case_results)
    old_summary = summarize_variant([case["old"] for case in case_results])
    v2_summary = summarize_variant([case["v2"] for case in case_results])
    comparison = compare_holdout_variants(case_results, old_summary, v2_summary)
    acceptance = evaluate_acceptance(old_summary, v2_summary, comparison)

    status = "PASS" if candidate_pool_parity and all(acceptance["checks"].values()) else "FAIL"
    if not candidate_pool_parity:
        status = "INVALID_EXPERIMENT"

    return {
        "experiment": "Reranker v2 Retrieval Holdout v1 First Frozen Validation",
        "dataset": str(HOLDOUT_PATH.relative_to(PROJECT_ROOT)),
        "protocol": str(PROTOCOL_PATH.relative_to(PROJECT_ROOT)),
        "reranker_v2_frozen_commit": RERANKER_V2_FROZEN_COMMIT,
        "holdout_frozen_commit": _git_last_commit(HOLDOUT_PATH),
        "protocol_frozen_commit": _git_last_commit(PROTOCOL_PATH),
        "evaluation_commit": _git_head(),
        "python_executable": sys.executable,
        "sentence_transformers_version": _package_version("sentence-transformers"),
        "bge_model": BGE_MODEL_NAME,
        "fallback_count": 0,
        "bge_fallback_used": False,
        "candidate_pool_parity": candidate_pool_parity,
        "metric_scope": {
            "evaluation_scope": "positive_only",
            "total_cases": 30,
            "gate_applied": False,
            "dedupe_level": "source",
            "top_k": TOP_K,
            "min_rerank_score": MIN_RERANK_SCORE,
            "only_variable": "reranker",
        },
        "dataset_composition": dict(
            sorted(Counter(case["category"] for case in cases).items())
        ),
        "fixed_variables": [
            "Knowledge Base V2",
            "Query Rewrite",
            "KeywordRetriever",
            "BGE VectorRetriever with BAAI/bge-small-zh",
            "HybridRetriever 0.5/0.5",
            "single shared candidate pool per case",
            "Top-K=5",
            "min_rerank_score=0.1",
            "source-level dedupe",
        ],
        "old_formula": BASELINE_FORMULA,
        "v2_formula": (
            "0.48 * retrieval_score + 0.17 * title_match + "
            "0.10 * source_match + 0.14 * keyword_overlap + domain_adjustment"
        ),
        "old": old_summary,
        "v2": v2_summary,
        "comparison": comparison,
        "acceptance": acceptance,
        "overall_status": status,
        "case_results": case_results,
    }


def build_bge_hybrid_retriever() -> HybridRetriever:
    from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

    bge_model = BGEEmbeddingModel(model_name=BGE_MODEL_NAME)
    return HybridRetriever(
        keyword_retriever=KeywordRetriever(),
        vector_retriever=VectorRetriever(embedding_model=bge_model),
    )


def evaluate_holdout_case(case: dict, hybrid_retriever, old_reranker, v2_reranker) -> dict:
    candidate_chunks = build_candidate_pool(case["event"], hybrid_retriever)
    old_input = _copy_chunks(candidate_chunks)
    v2_input = _copy_chunks(candidate_chunks)
    candidate_pool_parity = compare_candidate_pools(old_input, v2_input)

    old_result = _rerank_and_filter(case["event"], old_input, old_reranker)
    v2_result = _rerank_and_filter(case["event"], v2_input, v2_reranker)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "event": case["event"],
        "acceptable_sources": list(case["acceptable_sources"]),
        "neutral_sources": list(case["neutral_sources"]),
        "forbidden_sources": list(case["forbidden_sources"]),
        "rewritten_queries": rewrite_query(case["event"]),
        "candidate_pool_parity": candidate_pool_parity,
        "candidate_pool_signature": candidate_pool_signature(candidate_chunks),
        "old": evaluate_variant_result(case, old_result),
        "v2": evaluate_variant_result(case, v2_result),
    }


def build_candidate_pool(query: str, hybrid_retriever, top_k: int = TOP_K) -> list[RetrievedChunk]:
    rewritten_queries = rewrite_query(query)
    hybrid_chunks = []
    for rewritten_query in rewritten_queries:
        hybrid_result = hybrid_retriever.retrieve(rewritten_query, top_k=top_k)
        hybrid_chunks.extend(
            _copy_chunk_with_query_metadata(chunk, rewritten_query, rewritten_queries)
            for chunk in hybrid_result.chunks
        )
    return _merge_rewritten_chunks(hybrid_chunks)


def compare_candidate_pools(left: list[RetrievedChunk], right: list[RetrievedChunk]) -> bool:
    return candidate_pool_signature(left) == candidate_pool_signature(right)


def candidate_pool_signature(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "score": chunk.score,
            "embedding_score": chunk.embedding_score,
        }
        for chunk in chunks
    ]


def evaluate_variant_result(case: dict, retrieval: RetrievalResult) -> dict:
    deduped_sources = dedupe_sources([source.get("source", "") for source in retrieval.sources])
    metrics = calculate_case_metrics(
        deduped_sources,
        case["acceptable_sources"],
        case["neutral_sources"],
        case["forbidden_sources"],
    )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "acceptable_sources": list(case["acceptable_sources"]),
        "neutral_sources": list(case["neutral_sources"]),
        "forbidden_sources": list(case["forbidden_sources"]),
        "retrieval": retrieval.to_dict(),
        "deduped_sources": deduped_sources,
        "metrics": metrics,
    }


def calculate_case_metrics(
    sources: list[str],
    acceptable_sources: list[str],
    neutral_sources: list[str],
    forbidden_sources: list[str],
    k_values: tuple[int, ...] = (1, 3, 5),
) -> dict:
    acceptable = set(acceptable_sources)
    neutral = set(neutral_sources)
    forbidden = set(forbidden_sources)
    metrics = {}
    for k in k_values:
        metrics[f"recall_at_{k}"] = calculate_recall_at_k(sources, acceptable, k)
        metrics[f"precision_at_{k}"] = calculate_precision_at_k(sources, acceptable, k)
    metrics["reciprocal_rank"] = calculate_reciprocal_rank(sources, acceptable)
    metrics["source_category_match"] = calculate_source_category_match(
        sources,
        acceptable,
        forbidden,
    )
    metrics["context_pollution_rate"] = calculate_context_pollution_rate(
        sources,
        acceptable,
        neutral,
        forbidden,
    )
    metrics["has_acceptable_top1"] = bool(acceptable & set(sources[:1]))
    metrics["has_acceptable_top3"] = bool(acceptable & set(sources[:3]))
    metrics["has_forbidden"] = bool(forbidden & set(sources))
    metrics["source_count"] = len(sources)
    return metrics


def calculate_recall_at_k(sources: list[str], acceptable_sources: set[str], k: int) -> float:
    if not acceptable_sources:
        return 0.0
    hits = set(sources[:k]) & acceptable_sources
    return round(len(hits) / len(acceptable_sources), 4)


def calculate_precision_at_k(sources: list[str], acceptable_sources: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = set(sources[:k]) & acceptable_sources
    return round(len(hits) / k, 4)


def calculate_reciprocal_rank(sources: list[str], acceptable_sources: set[str]) -> float:
    for index, source in enumerate(sources, start=1):
        if source in acceptable_sources:
            return round(1 / index, 4)
    return 0.0


def calculate_source_category_match(
    sources: list[str],
    acceptable_sources: set[str],
    forbidden_sources: set[str],
) -> float:
    acceptable_count = sum(1 for source in sources if source in acceptable_sources)
    forbidden_count = sum(1 for source in sources if source in forbidden_sources)
    denominator = acceptable_count + forbidden_count
    if denominator == 0:
        return 0.0
    return round(acceptable_count / denominator, 4)


def calculate_context_pollution_rate(
    sources: list[str],
    acceptable_sources: set[str],
    neutral_sources: set[str],
    forbidden_sources: set[str],
) -> float:
    acceptable_count = sum(1 for source in sources if source in acceptable_sources)
    neutral_count = sum(1 for source in sources if source in neutral_sources)
    forbidden_count = sum(1 for source in sources if source in forbidden_sources)
    denominator = acceptable_count + neutral_count + forbidden_count
    if denominator == 0:
        return 0.0
    return round(forbidden_count / denominator, 4)


def summarize_variant(case_variants: list[dict]) -> dict:
    metrics = [case["metrics"] for case in case_variants]
    summary = {
        "total_cases": len(case_variants),
        "recall_at_1": _average([item["recall_at_1"] for item in metrics]),
        "recall_at_3": _average([item["recall_at_3"] for item in metrics]),
        "recall_at_5": _average([item["recall_at_5"] for item in metrics]),
        "precision_at_1": _average([item["precision_at_1"] for item in metrics]),
        "precision_at_3": _average([item["precision_at_3"] for item in metrics]),
        "precision_at_5": _average([item["precision_at_5"] for item in metrics]),
        "mrr": _average([item["reciprocal_rank"] for item in metrics]),
        "source_category_match": _average([item["source_category_match"] for item in metrics]),
        "context_pollution_rate": _average([item["context_pollution_rate"] for item in metrics]),
        "acceptable_top1_count": sum(1 for item in metrics if item["has_acceptable_top1"]),
        "acceptable_top3_count": sum(1 for item in metrics if item["has_acceptable_top3"]),
        "pollution_case_count": sum(1 for item in metrics if item["has_forbidden"]),
        "wrong_rank_distribution": count_wrong_by_rank(case_variants),
        "confusion_pairs": count_confusion_pairs(case_variants),
    }
    return summary


def summarize_variant_by_category(case_results: list[dict], variant_name: str) -> dict:
    grouped: dict[str, list[dict]] = {}
    for case in case_results:
        grouped.setdefault(case["category"], []).append(case[variant_name])
    return {
        category: {
            "recall_at_1": summary["recall_at_1"],
            "recall_at_3": summary["recall_at_3"],
            "mrr": summary["mrr"],
            "source_category_match": summary["source_category_match"],
            "context_pollution_rate": summary["context_pollution_rate"],
        }
        for category, summary in (
            (category, summarize_variant(items))
            for category, items in sorted(grouped.items())
        )
    }


def compare_holdout_variants(case_results: list[dict], old_summary: dict, v2_summary: dict) -> dict:
    top3_regressions = []
    improvement_cases = []
    pollution_improvements = []
    newly_introduced_pollution = []

    for case in case_results:
        old_sources = case["old"]["deduped_sources"]
        v2_sources = case["v2"]["deduped_sources"]
        acceptable = set(case["acceptable_sources"])
        forbidden = set(case["forbidden_sources"])
        old_top3_hit = bool(acceptable & set(old_sources[:3]))
        v2_top3_hit = bool(acceptable & set(v2_sources[:3]))
        old_forbidden = sorted(forbidden & set(old_sources))
        v2_forbidden = sorted(forbidden & set(v2_sources))

        if old_top3_hit and not v2_top3_hit:
            top3_regressions.append(_case_comparison_summary(case))
        if not old_top3_hit and v2_top3_hit:
            improvement_cases.append(_case_comparison_summary(case))
        if old_forbidden and len(v2_forbidden) < len(old_forbidden):
            item = _case_comparison_summary(case)
            item["old_forbidden_sources"] = old_forbidden
            item["v2_forbidden_sources"] = v2_forbidden
            pollution_improvements.append(item)
        if not old_forbidden and v2_forbidden:
            item = _case_comparison_summary(case)
            item["v2_forbidden_sources"] = v2_forbidden
            newly_introduced_pollution.append(item)

    pollution_reduction = calculate_relative_pollution_reduction(
        old_summary["context_pollution_rate"],
        v2_summary["context_pollution_rate"],
    )
    return {
        "metric_differences": metric_differences(old_summary, v2_summary),
        "pollution_relative_reduction": pollution_reduction,
        "top3_retrieval_regressions": top3_regressions,
        "new_top3_regression_count": len(top3_regressions),
        "improvement_cases": improvement_cases,
        "pollution_improvement_cases": pollution_improvements,
        "newly_introduced_pollution": newly_introduced_pollution,
        "per_domain_old": summarize_variant_by_category(case_results, "old"),
        "per_domain_v2": summarize_variant_by_category(case_results, "v2"),
    }


def evaluate_acceptance(old_summary: dict, v2_summary: dict, comparison: dict) -> dict:
    per_domain_v2 = comparison["per_domain_v2"]
    old_pollution = old_summary["context_pollution_rate"]
    relative_reduction = comparison["pollution_relative_reduction"]
    checks = {
        "v2_recall_at_3_min": v2_summary["recall_at_3"] >= 0.90,
        "recall_at_3_drop_within_0_05": (
            old_summary["recall_at_3"] - v2_summary["recall_at_3"]
        ) <= 0.05,
        "context_pollution_lower_than_old": (
            v2_summary["context_pollution_rate"] < old_pollution
        ),
        "pollution_relative_reduction_at_least_20_percent": (
            relative_reduction is not None and relative_reduction >= 0.20
        ),
        "source_category_match_higher_than_old": (
            v2_summary["source_category_match"] > old_summary["source_category_match"]
        ),
        "new_top3_regression_cases_lte_2": (
            comparison["new_top3_regression_count"] <= 2
        ),
        "each_domain_recall_at_3_at_least_0_75": all(
            metrics["recall_at_3"] >= 0.75
            for metrics in per_domain_v2.values()
        ),
    }
    return {
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "notes": (
            "If old context pollution is 0, relative reduction is undefined and "
            "the pollution reduction criterion fails."
        ),
    }


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def build_markdown_report(result: dict) -> str:
    old = result["old"]
    v2 = result["v2"]
    comparison = result["comparison"]
    acceptance = result["acceptance"]
    lines = [
        "# Reranker v2 Retrieval Holdout v1 First Frozen Validation",
        "",
        "## Metadata",
        "",
        f"- experiment: `{result['experiment']}`",
        f"- dataset: `{result['dataset']}`",
        f"- protocol: `{result['protocol']}`",
        f"- reranker_v2_frozen_commit: `{result['reranker_v2_frozen_commit']}`",
        f"- holdout_frozen_commit: `{result['holdout_frozen_commit']}`",
        f"- protocol_frozen_commit: `{result['protocol_frozen_commit']}`",
        f"- evaluation_commit: `{result['evaluation_commit']}`",
        f"- python_executable: `{result['python_executable']}`",
        f"- sentence_transformers_version: `{result['sentence_transformers_version']}`",
        f"- bge_model: `{result['bge_model']}`",
        f"- bge_fallback_used: `{result['bge_fallback_used']}`",
        f"- fallback_count: `{result['fallback_count']}`",
        f"- candidate_pool_parity: `{result['candidate_pool_parity']}`",
        "",
        "## Metric Scope",
        "",
    ]
    for key, value in result["metric_scope"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Dataset Composition",
            "",
            f"- {result['dataset_composition']}",
            "",
            "## Fixed Variables",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in result["fixed_variables"])
    lines.extend(
        [
            "",
            "## Formulas",
            "",
            f"- Old Reranker: `{result['old_formula']}`",
            f"- Reranker v2: `{result['v2_formula']}`",
            "",
            "## Metric Comparison",
            "",
            "| Metric | Old | Reranker v2 | Difference |",
            "|---|---:|---:|---:|",
        ]
    )
    for metric, diff in comparison["metric_differences"].items():
        lines.append(f"| {metric} | `{old.get(metric)}` | `{v2.get(metric)}` | `{diff}` |")
    lines.extend(
        [
            f"| pollution_relative_reduction | `-` | `{comparison['pollution_relative_reduction']}` | `-` |",
            "",
            "## Per-Domain Metrics",
            "",
            "| Category | Old Recall@3 | v2 Recall@3 | Old MRR | v2 MRR | Old SCM | v2 SCM | Old Pollution | v2 Pollution |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for category in sorted(comparison["per_domain_v2"]):
        old_domain = comparison["per_domain_old"][category]
        v2_domain = comparison["per_domain_v2"][category]
        lines.append(
            f"| {category} | `{old_domain['recall_at_3']}` | `{v2_domain['recall_at_3']}` | "
            f"`{old_domain['mrr']}` | `{v2_domain['mrr']}` | "
            f"`{old_domain['source_category_match']}` | `{v2_domain['source_category_match']}` | "
            f"`{old_domain['context_pollution_rate']}` | `{v2_domain['context_pollution_rate']}` |"
        )
    lines.extend(
        [
            "",
            "## Cross-Domain Confusion",
            "",
            f"- Old: `{old['confusion_pairs']}`",
            f"- Reranker v2: `{v2['confusion_pairs']}`",
            "",
            "## Wrong-Category Rank Distribution",
            "",
            f"- Old: `{old['wrong_rank_distribution']}`",
            f"- Reranker v2: `{v2['wrong_rank_distribution']}`",
            "",
            "## Regression and Improvement Cases",
            "",
            f"- new_top3_regression_count: `{comparison['new_top3_regression_count']}`",
            f"- top3_retrieval_regressions: `{comparison['top3_retrieval_regressions']}`",
            f"- improvement_cases: `{comparison['improvement_cases']}`",
            f"- pollution_improvement_cases: `{comparison['pollution_improvement_cases']}`",
            f"- newly_introduced_pollution: `{comparison['newly_introduced_pollution']}`",
            "",
            "## Primary Criteria",
            "",
        ]
    )
    for name, passed in acceptance["checks"].items():
        lines.append(f"- `{name}`: `{'PASS' if passed else 'FAIL'}`")
    lines.extend(
        [
            f"- Overall Result: `{acceptance['status']}`",
            "",
            "## Historical Development Context",
            "",
            "- Phase 4B Development was Challenge v3 post-hoc development only.",
            "- Development Recall@3: `0.95 -> 0.95`",
            "- Development Context Pollution: `0.4314 -> 0.1765`",
            "- Development Source Category Match: `0.3921 -> 0.5882`",
            "- These development numbers are not mixed with Retrieval Holdout v1 before/after metrics.",
            "",
            "## Limitations",
            "",
            "- Retrieval Holdout v1 is no longer untouched after this first formal run.",
            "- This report isolates Reranker behavior and does not apply Retrieval Need Gate.",
            "- Any future Reranker change requires a new frozen retrieval holdout.",
        ]
    )
    return "\n".join(lines) + "\n"


def _rerank_and_filter(query: str, chunks: list[RetrievedChunk], reranker) -> RetrievalResult:
    reranked = reranker.rerank(query, chunks, top_k=TOP_K)
    kept_chunks = [
        chunk for chunk in reranked.chunks
        if _final_relevance_score(chunk) >= MIN_RERANK_SCORE
    ]
    return RetrievalResult(
        context=_format_context(kept_chunks),
        chunks=kept_chunks,
        sources=[_source_dict(chunk) for chunk in kept_chunks],
    )


def _final_relevance_score(chunk: RetrievedChunk) -> float:
    metadata = chunk.metadata or {}
    score = metadata.get("rerank_score", chunk.rerank_score)
    if score is None:
        score = chunk.score
    return float(score or 0.0)


def _copy_chunk_with_query_metadata(
    chunk: RetrievedChunk,
    matched_query: str,
    rewritten_queries: list[str],
) -> RetrievedChunk:
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "query_rewrite_enabled": True,
            "matched_query": matched_query,
            "rewritten_queries": list(rewritten_queries),
        }
    )
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=chunk.rerank_score,
    )


def _copy_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            source=chunk.source,
            title=chunk.title,
            score=chunk.score,
            metadata=copy.deepcopy(chunk.metadata or {}),
            embedding_score=chunk.embedding_score,
            rerank_score=chunk.rerank_score,
        )
        for chunk in chunks
    ]


def dedupe_sources(sources: list[str]) -> list[str]:
    deduped = []
    for source in sources:
        if source and source not in deduped:
            deduped.append(source)
    return deduped


def count_wrong_by_rank(case_variants: list[dict]) -> dict:
    counts = Counter()
    for case in case_variants:
        forbidden = set(case.get("forbidden_sources", []))
        for rank, source in enumerate(case["deduped_sources"], start=1):
            if source in forbidden:
                counts[f"rank{rank}"] += 1
    return {f"rank{rank}": counts.get(f"rank{rank}", 0) for rank in range(1, TOP_K + 1)}


def count_confusion_pairs(case_variants: list[dict]) -> dict:
    counts = Counter()
    for case in case_variants:
        expected_domain = case["category"]
        for source in case["deduped_sources"]:
            if source in set(case.get("forbidden_sources", [])):
                counts[f"{expected_domain}->{source}"] += 1
    return dict(counts.most_common())


def metric_differences(old_summary: dict, v2_summary: dict) -> dict:
    metrics = [
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_1",
        "precision_at_3",
        "precision_at_5",
        "mrr",
        "source_category_match",
        "context_pollution_rate",
        "acceptable_top1_count",
        "acceptable_top3_count",
        "pollution_case_count",
    ]
    return {
        metric: round((v2_summary.get(metric) or 0.0) - (old_summary.get(metric) or 0.0), 4)
        for metric in metrics
    }


def calculate_relative_pollution_reduction(old_pollution: float, v2_pollution: float):
    if old_pollution == 0:
        return None
    return round((old_pollution - v2_pollution) / old_pollution, 4)


def _case_comparison_summary(case: dict) -> dict:
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "event": case["event"],
        "acceptable_sources": case["acceptable_sources"],
        "old_top3": case["old"]["deduped_sources"][:3],
        "v2_top3": case["v2"]["deduped_sources"][:3],
    }


def _validate_source_groups(case: dict) -> None:
    acceptable = set(case.get("acceptable_sources", []))
    neutral = set(case.get("neutral_sources", []))
    forbidden = set(case.get("forbidden_sources", []))
    if acceptable & neutral or acceptable & forbidden or neutral & forbidden:
        raise ValueError(f"Case {case.get('case_id')} source groups must be mutually exclusive.")


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not_installed"


def _git_head() -> str:
    return _run_git(["rev-parse", "--short", "HEAD"])


def _git_last_commit(path: Path) -> str:
    return _run_git(["log", "-1", "--format=%h", "--", str(path.relative_to(PROJECT_ROOT))])


def _run_git(args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    try:
        result = run_holdout_evaluation()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "INVALID_EXPERIMENT",
                    "reason": type(exc).__name__,
                    "message": str(exc),
                    "bge_fallback_used": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    report_path = save_report(result)
    print(
        json.dumps(
            {
                "status": result["overall_status"],
                "report_path": str(report_path),
                "candidate_pool_parity": result["candidate_pool_parity"],
                "fallback_count": result["fallback_count"],
                "old": result["old"],
                "v2": result["v2"],
                "comparison": {
                    "pollution_relative_reduction": result["comparison"]["pollution_relative_reduction"],
                    "new_top3_regression_count": result["comparison"]["new_top3_regression_count"],
                },
                "acceptance": result["acceptance"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
