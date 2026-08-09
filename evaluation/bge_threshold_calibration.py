import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.reranker import RuleBasedReranker
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_retriever import VectorRetriever
from evaluation.rag_evaluator_v2 import DEFAULT_CASES_PATH, load_cases
from evaluation.rag_metrics_v2 import evaluate_retrieval_case, summarize_subset


NEGATIVE_CASES_PATH = PROJECT_ROOT / "evaluation" / "rag_negative_calibration_v2.json"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_bge_threshold_calibration.md"
TOP_K = 5
DEFAULT_PRODUCTION_THRESHOLD = 0.1
THRESHOLDS = (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30)
SOURCE_CATEGORIES = {
    "food_safety.md": "food_safety",
    "data_privacy.md": "data_privacy",
    "service_outage.md": "service_outage",
    "product_quality.md": "product_quality",
    "executive_misconduct.md": "executive_misconduct",
    "crisis_response.md": "general_crisis_response",
    "legal_risk_rules.md": "legal_risk_rules",
}


class DisabledFallbackRetriever:
    def retrieve(self, query: str, top_k: int = TOP_K) -> RetrievalResult:
        raise RuntimeError("Fallback is disabled for BGE threshold calibration.")


def load_negative_cases(path: str | Path = NEGATIVE_CASES_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_calibration(
    positive_cases_path: str | Path = DEFAULT_CASES_PATH,
    negative_cases_path: str | Path = NEGATIVE_CASES_PATH,
    thresholds: tuple[float, ...] = THRESHOLDS,
) -> dict:
    positive_cases = [case for case in load_cases(positive_cases_path) if case["split"] == "development"]
    negative_cases = load_negative_cases(negative_cases_path)
    validate_negative_cases(negative_cases)

    bge_model = BGEEmbeddingModel()
    vector_retriever = VectorRetriever(embedding_model=bge_model)

    distribution_pipeline = build_pipeline(vector_retriever, min_rerank_score=0.0)
    positive_distribution = collect_score_distribution(positive_cases, distribution_pipeline, vector_retriever)
    negative_distribution = collect_score_distribution(negative_cases, distribution_pipeline, vector_retriever)

    sweep = []
    baseline = None
    for threshold in thresholds:
        pipeline = build_pipeline(vector_retriever, min_rerank_score=threshold)
        threshold_result = evaluate_threshold(threshold, positive_cases, negative_cases, pipeline)
        if threshold == DEFAULT_PRODUCTION_THRESHOLD:
            baseline = threshold_result
        sweep.append(threshold_result)

    if baseline is None:
        raise RuntimeError("Default production threshold is missing from threshold sweep.")
    for item in sweep:
        item["positive_recall_loss"] = round(
            baseline["positive"]["summary"]["recall_at_3"] - item["positive"]["summary"]["recall_at_3"],
            4,
        )
        item["negative_false_positive_reduction"] = (
            baseline["negative"]["false_positive_count"] - item["negative"]["false_positive_count"]
        )

    recommendation = recommend_threshold(sweep)
    return {
        "experiment": "BGE No-hit / Threshold Calibration",
        "bge_model": "BAAI/bge-small-zh",
        "split": "development",
        "old_final_run": False,
        "production_threshold_unchanged": DEFAULT_PRODUCTION_THRESHOLD,
        "top_k": TOP_K,
        "positive_case_count": len(positive_cases),
        "negative_case_count": len(negative_cases),
        "negative_type_counts": count_negative_types(negative_cases),
        "positive_score_distribution": summarize_scores(positive_distribution),
        "negative_score_distribution": summarize_negative_scores(negative_distribution),
        "threshold_sweep": sweep,
        "recommendation": recommendation,
        "hardest_hard_negatives": hardest_negatives(negative_distribution, "hard_negative", limit=5),
    }


def build_pipeline(vector_retriever: VectorRetriever, min_rerank_score: float) -> RagPipelineRetriever:
    return RagPipelineRetriever(
        hybrid_retriever=HybridRetriever(
            keyword_retriever=KeywordRetriever(),
            vector_retriever=vector_retriever,
        ),
        reranker=RuleBasedReranker(),
        fallback_retriever=DisabledFallbackRetriever(),
        min_rerank_score=min_rerank_score,
    )


def evaluate_threshold(
    threshold: float,
    positive_cases: list[dict],
    negative_cases: list[dict],
    pipeline: RagPipelineRetriever,
) -> dict:
    positive_results = [evaluate_case(case, pipeline) for case in positive_cases]
    negative_results = [evaluate_case(case, pipeline) for case in negative_cases]
    return {
        "threshold": threshold,
        "positive": {
            "summary": summarize_subset(positive_results),
            "case_results": positive_results,
        },
        "negative": summarize_negative_results(negative_results),
    }


def evaluate_case(case: dict, pipeline: RagPipelineRetriever) -> dict:
    retrieval = pipeline.retrieve(case["query"], top_k=TOP_K).to_dict()
    metrics = evaluate_retrieval_case(case, retrieval)
    return {
        "id": case["id"],
        "split": case.get("split", "calibration"),
        "category": case.get("category", case.get("type", "unknown")),
        "type": case.get("type"),
        "query": case["query"],
        "acceptable_sources": case.get("acceptable_sources", []),
        "expected_hit": case.get("expected_hit", True),
        "forbidden_sources": case.get("forbidden_sources", []),
        "forbidden_categories": case.get("forbidden_categories", []),
        "retrieval": retrieval,
        "metrics": metrics,
    }


def collect_score_distribution(
    cases: list[dict],
    pipeline: RagPipelineRetriever,
    vector_retriever: VectorRetriever,
) -> list[dict]:
    distributions = []
    for case in cases:
        retrieval = pipeline.retrieve(case["query"], top_k=TOP_K).to_dict()
        vector_retrieval = vector_retriever.retrieve(case["query"], top_k=TOP_K).to_dict()
        sources = retrieval.get("sources", [])
        vector_sources = vector_retrieval.get("sources", [])
        distributions.append(
            {
                "id": case["id"],
                "type": case.get("type"),
                "category": case.get("category", case.get("type", "unknown")),
                "query": case["query"],
                "top1_rerank_score": _source_score(sources, "rerank_score", 0),
                "top3_rerank_scores": [_source_score(sources, "rerank_score", index) for index in range(3)],
                "vector_top_sources": [source.get("source") for source in vector_sources],
                "vector_scores": [_source_score(vector_sources, "score", index) for index in range(len(vector_sources))],
                "hybrid_scores": [source.get("score") for source in sources],
                "final_sources": [source.get("source") for source in sources],
                "final_categories": [
                    SOURCE_CATEGORIES.get(source.get("source"), "unknown")
                    for source in sources
                ],
            }
        )
    return distributions


def summarize_negative_results(case_results: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for case in case_results:
        grouped.setdefault(case["type"], []).append(case)

    return {
        "case_count": len(case_results),
        "no_hit_accuracy": no_hit_accuracy(case_results),
        "false_positive_count": false_positive_count(case_results),
        "type_metrics": {
            case_type: {
                "case_count": len(items),
                "no_hit_accuracy": no_hit_accuracy(items),
                "false_positive_count": false_positive_count(items),
            }
            for case_type, items in sorted(grouped.items())
        },
        "case_results": case_results,
    }


def no_hit_accuracy(case_results: list[dict]) -> float:
    if not case_results:
        return 0.0
    correct = sum(1 for case in case_results if case["metrics"].get("no_hit_correct"))
    return round(correct / len(case_results), 4)


def false_positive_count(case_results: list[dict]) -> int:
    return sum(1 for case in case_results if not case["metrics"].get("no_hit_correct"))


def summarize_scores(distributions: list[dict]) -> dict:
    scores = [item["top1_rerank_score"] for item in distributions if item["top1_rerank_score"] is not None]
    return _score_stats(scores)


def summarize_negative_scores(distributions: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for item in distributions:
        grouped.setdefault(item["type"], []).append(item)
    return {
        "overall": summarize_scores(distributions),
        "by_type": {
            case_type: summarize_scores(items)
            for case_type, items in sorted(grouped.items())
        },
    }


def recommend_threshold(sweep: list[dict]) -> dict:
    candidates = []
    for item in sweep:
        recall_at_3 = item["positive"]["summary"]["recall_at_3"]
        no_hit = item["negative"]["no_hit_accuracy"]
        hard_no_hit = item["negative"]["type_metrics"]["hard_negative"]["no_hit_accuracy"]
        pollution = item["positive"]["summary"]["context_pollution_rate"]
        if recall_at_3 >= 0.6 and no_hit >= 0.5 and hard_no_hit >= 0.25:
            candidates.append((item["threshold"], recall_at_3, no_hit, hard_no_hit, pollution))

    if not candidates:
        return {
            "recommended_threshold": None,
            "backup_threshold": None,
            "trade_off": "No clear Pareto point found. BGE needs an additional no-hit gate or retrieval confidence gate.",
            "needs_no_hit_gate": True,
        }

    candidates.sort(key=lambda value: (value[0], -value[1]))
    recommended = candidates[0]
    backup = candidates[1] if len(candidates) > 1 else recommended
    return {
        "recommended_threshold": recommended[0],
        "backup_threshold": backup[0],
        "trade_off": (
            "Selected the lowest threshold that keeps Recall@3 reasonably high while improving negative no-hit behavior. "
            "Further no-hit gate validation is still recommended."
        ),
        "needs_no_hit_gate": True,
    }


def hardest_negatives(distributions: list[dict], case_type: str, limit: int = 5) -> list[dict]:
    items = [item for item in distributions if item["type"] == case_type]
    return sorted(items, key=lambda item: item["top1_rerank_score"] or 0.0, reverse=True)[:limit]


def validate_negative_cases(cases: list[dict]) -> None:
    if len(cases) != 24:
        raise ValueError("Negative calibration set must contain 24 cases.")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Negative calibration case ids must be unique.")
    type_counts = count_negative_types(cases)
    expected = {"unrelated": 8, "business_non_crisis": 8, "hard_negative": 8}
    if type_counts != expected:
        raise ValueError(f"Negative calibration type counts must be {expected}, got {type_counts}.")
    if any(case.get("expected_hit") is not False for case in cases):
        raise ValueError("All negative calibration cases must set expected_hit=false.")


def count_negative_types(cases: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["type"]] = counts.get(case["type"], 0) + 1
    return dict(sorted(counts.items()))


def build_markdown_report(result: dict) -> str:
    lines = [
        "# CrisisAgent BGE Threshold Calibration",
        "",
        "## Experiment",
        "",
        "- Python executable: `C:\\Users\\19726\\Documents\\CrisisAgent\\.venv\\Scripts\\python.exe`",
        "- sentence-transformers: `5.7.0`",
        "- HF_HOME: `C:\\Users\\19726\\Documents\\hf-cache`",
        f"- BGE model: `{result['bge_model']}`",
        f"- split: `{result['split']}`",
        f"- old Final Set run: `{result['old_final_run']}`",
        f"- production min_rerank_score unchanged: `{result['production_threshold_unchanged']}`",
        f"- negative calibration cases: `{result['negative_case_count']}`",
        f"- negative type counts: `{result['negative_type_counts']}`",
        "",
        "## Score Distribution",
        "",
        f"- Positive top1 rerank score: `{result['positive_score_distribution']}`",
        f"- Negative overall top1 rerank score: `{result['negative_score_distribution']['overall']}`",
    ]
    for case_type, stats in result["negative_score_distribution"]["by_type"].items():
        lines.append(f"- {case_type} top1 rerank score: `{stats}`")

    lines.extend(
        [
            "",
            "## Threshold Sweep",
            "",
            "| threshold | Recall@3 | MRR | No-hit overall | unrelated | business | hard_negative | Pollution | FP Count | Recall Loss | FP Reduction |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in result["threshold_sweep"]:
        negative = item["negative"]
        positive = item["positive"]["summary"]
        type_metrics = negative["type_metrics"]
        lines.append(
            f"| {item['threshold']} | {positive['recall_at_3']} | {positive['mrr']} | "
            f"{negative['no_hit_accuracy']} | {type_metrics['unrelated']['no_hit_accuracy']} | "
            f"{type_metrics['business_non_crisis']['no_hit_accuracy']} | "
            f"{type_metrics['hard_negative']['no_hit_accuracy']} | "
            f"{positive['context_pollution_rate']} | {negative['false_positive_count']} | "
            f"{item['positive_recall_loss']} | {item['negative_false_positive_reduction']} |"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- recommended_threshold: `{result['recommendation']['recommended_threshold']}`",
            f"- backup_threshold: `{result['recommendation']['backup_threshold']}`",
            f"- trade_off: {result['recommendation']['trade_off']}",
            f"- needs_no_hit_gate: `{result['recommendation']['needs_no_hit_gate']}`",
            "- conclusion: Positive and negative top1 rerank score distributions overlap clearly. "
            "A single min_rerank_score threshold cannot keep both high Recall and high No-hit accuracy in this experiment.",
            "- next_step: Do not treat 0.20 or 0.22 as a final recommended threshold. "
            "The next experiment should add an independent retrieval-need / no-hit gate.",
            "",
            "## Hardest Hard Negatives",
            "",
        ]
    )
    for item in result["hardest_hard_negatives"]:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- query: `{item['query']}`",
                f"- top1_rerank_score: `{item['top1_rerank_score']}`",
                f"- top3_rerank_scores: `{item['top3_rerank_scores']}`",
                f"- vector_top_sources: `{item['vector_top_sources']}`",
                f"- vector_scores: `{item['vector_scores']}`",
                f"- final_sources: `{item['final_sources']}`",
                f"- final_categories: `{item['final_categories']}`",
                "",
            ]
        )
    return "\n".join(lines)


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def _score_stats(scores: list[float]) -> dict:
    if not scores:
        return {key: 0.0 for key in ("min", "p10", "p25", "median", "p75", "p90", "p95", "max")}
    sorted_scores = sorted(scores)
    return {
        "min": round(min(sorted_scores), 4),
        "p10": round(_percentile(sorted_scores, 0.10), 4),
        "p25": round(_percentile(sorted_scores, 0.25), 4),
        "median": round(statistics.median(sorted_scores), 4),
        "p75": round(_percentile(sorted_scores, 0.75), 4),
        "p90": round(_percentile(sorted_scores, 0.90), 4),
        "p95": round(_percentile(sorted_scores, 0.95), 4),
        "max": round(max(sorted_scores), 4),
    }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[int(index)]
    return sorted_values[lower] * (upper - index) + sorted_values[upper] * (index - lower)


def _source_score(sources: list[dict], field: str, index: int) -> float | None:
    if index >= len(sources):
        return None
    value = sources[index].get(field)
    return round(float(value), 4) if value is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BGE no-hit / threshold calibration.")
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args()

    try:
        result = run_calibration()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "INVALID_EXPERIMENT",
                    "reason": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    report_path = save_report(result, args.output)
    printable = {
        "status": "OK",
        "report_path": str(report_path),
        "positive_score_distribution": result["positive_score_distribution"],
        "negative_score_distribution": result["negative_score_distribution"],
        "threshold_sweep": [
            {
                "threshold": item["threshold"],
                "recall_at_3": item["positive"]["summary"]["recall_at_3"],
                "mrr": item["positive"]["summary"]["mrr"],
                "no_hit_accuracy": item["negative"]["no_hit_accuracy"],
                "unrelated_no_hit": item["negative"]["type_metrics"]["unrelated"]["no_hit_accuracy"],
                "business_no_hit": item["negative"]["type_metrics"]["business_non_crisis"]["no_hit_accuracy"],
                "hard_negative_no_hit": item["negative"]["type_metrics"]["hard_negative"]["no_hit_accuracy"],
                "pollution": item["positive"]["summary"]["context_pollution_rate"],
                "false_positive_count": item["negative"]["false_positive_count"],
            }
            for item in result["threshold_sweep"]
        ],
        "recommendation": result["recommendation"],
        "hardest_hard_negatives": result["hardest_hard_negatives"],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
