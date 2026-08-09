import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.embedding import EmbeddingModel
from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel
from backend.rag.embeddings.hash_embedding import HashEmbeddingModel
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.reranker import RuleBasedReranker
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_retriever import VectorRetriever
from evaluation.rag_evaluator_v2 import DEFAULT_CASES_PATH, load_cases
from evaluation.rag_metrics_v2 import evaluate_retrieval_case, summarize_subset


REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_embedding_ablation_hash_vs_bge.md"
TOP_K = 5
MIN_RERANK_SCORE = 0.1


@dataclass
class TimedEmbeddingModel(EmbeddingModel):
    model: EmbeddingModel
    query_latencies_ms: list[float] = field(default_factory=list)
    recording_enabled: bool = False

    def embed(self, text: str) -> list[float]:
        started_at = time.perf_counter()
        vector = self.model.embed(text)
        elapsed_ms = _elapsed_ms(started_at)
        if self.recording_enabled:
            self.query_latencies_ms.append(elapsed_ms)
        return vector

    def reset_query_latencies(self) -> None:
        self.query_latencies_ms = []


class DisabledFallbackRetriever:
    def retrieve(self, query: str, top_k: int = TOP_K) -> RetrievalResult:
        raise RuntimeError("Fallback is disabled for embedding ablation.")


def run_ablation(cases_path: str | Path = DEFAULT_CASES_PATH, split: str = "development") -> dict:
    cases = [case for case in load_cases(cases_path) if case["split"] == split]
    case_ids = [case["id"] for case in cases]

    hash_result = evaluate_embedding_model("hash", cases)
    bge_result = evaluate_embedding_model("bge", cases)

    if case_ids != [case["id"] for case in hash_result["case_results"]]:
        raise RuntimeError("Hash case order changed during evaluation.")
    if case_ids != [case["id"] for case in bge_result["case_results"]]:
        raise RuntimeError("BGE case order changed during evaluation.")
    if bge_result["summary"]["fallback_count"] > 0:
        raise RuntimeError("INVALID_EXPERIMENT: BGE retrieval used fallback.")

    result = {
        "experiment": "HashEmbedding vs BGEEmbedding",
        "split": split,
        "top_k": TOP_K,
        "min_rerank_score": MIN_RERANK_SCORE,
        "fixed_variables": {
            "knowledge_base": "Knowledge Base V2",
            "cases": str(Path(cases_path)),
            "keyword_retriever": "KeywordRetriever",
            "vector_store": "VectorStore",
            "hybrid_retriever": "HybridRetriever",
            "hybrid_weights": {"keyword": 0.5, "vector": 0.5},
            "reranker": "RuleBasedReranker",
            "query_rewrite": True,
        },
        "hash": hash_result,
        "bge": bge_result,
    }
    result["comparison"] = compare_summaries(hash_result["summary"], bge_result["summary"])
    result["case_comparison"] = compare_cases(hash_result["case_results"], bge_result["case_results"])
    return result


def evaluate_embedding_model(model_name: str, cases: list[dict]) -> dict:
    model_started_at = time.perf_counter()
    if model_name == "hash":
        base_model = HashEmbeddingModel()
    elif model_name == "bge":
        base_model = BGEEmbeddingModel()
    else:
        raise ValueError("model_name must be hash or bge.")
    model_initialization_ms = _elapsed_ms(model_started_at)

    timed_model = TimedEmbeddingModel(base_model)
    vector_retriever = VectorRetriever(embedding_model=timed_model)
    pipeline = RagPipelineRetriever(
        hybrid_retriever=HybridRetriever(
            keyword_retriever=KeywordRetriever(),
            vector_retriever=vector_retriever,
        ),
        reranker=RuleBasedReranker(),
        fallback_retriever=DisabledFallbackRetriever(),
        min_rerank_score=MIN_RERANK_SCORE,
    )

    warmup_query = cases[0]["query"] if cases else "食品安全"
    pipeline.retrieve(warmup_query, top_k=TOP_K)
    timed_model.reset_query_latencies()
    timed_model.recording_enabled = True

    case_results = []
    total_retrieval_latencies = []
    for case in cases:
        vector_result = vector_retriever.retrieve(case["query"], top_k=TOP_K).to_dict()
        started_at = time.perf_counter()
        retrieval = pipeline.retrieve(case["query"], top_k=TOP_K).to_dict()
        total_retrieval_latencies.append(_elapsed_ms(started_at))
        metrics = evaluate_retrieval_case(case, retrieval)
        case_results.append(
            {
                "id": case["id"],
                "split": case["split"],
                "category": case["category"],
                "query": case["query"],
                "acceptable_sources": case.get("acceptable_sources", []),
                "expected_hit": case.get("expected_hit", True),
                "forbidden_sources": case.get("forbidden_sources", []),
                "forbidden_categories": case.get("forbidden_categories", []),
                "vector_top_results": vector_result.get("sources", []),
                "retrieval": retrieval,
                "metrics": metrics,
            }
        )

    summary = summarize_subset(case_results)
    categories = {
        category: summarize_subset([case for case in case_results if case["category"] == category])
        for category in sorted({case["category"] for case in case_results})
    }
    return {
        "model": model_name,
        "model_initialization_ms": round(model_initialization_ms, 2),
        "summary": summary,
        "categories": categories,
        "performance": {
            "query_embedding_latency_ms": summarize_latencies(timed_model.query_latencies_ms),
            "total_retrieval_latency_ms": summarize_latencies(total_retrieval_latencies),
            "query_embedding_call_count": len(timed_model.query_latencies_ms),
        },
        "case_results": case_results,
    }


def compare_summaries(hash_summary: dict, bge_summary: dict) -> dict:
    metrics = [
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_1",
        "precision_at_3",
        "precision_at_5",
        "mrr",
        "no_hit_accuracy",
        "source_category_match",
        "context_pollution_rate",
        "fallback_count",
    ]
    return {
        metric: _diff(hash_summary.get(metric, 0), bge_summary.get(metric, 0))
        for metric in metrics
    }


def compare_cases(hash_cases: list[dict], bge_cases: list[dict]) -> dict:
    comparisons = []
    for hash_case, bge_case in zip(hash_cases, bge_cases):
        if hash_case["id"] != bge_case["id"]:
            raise RuntimeError("Case order mismatch.")
        delta = _case_quality_score(bge_case) - _case_quality_score(hash_case)
        comparisons.append(
            {
                "case_id": hash_case["id"],
                "category": hash_case["category"],
                "query": hash_case["query"],
                "delta": round(delta, 4),
                "reason": classify_case_change(hash_case, bge_case, delta),
                "hash": _case_trace(hash_case),
                "bge": _case_trace(bge_case),
            }
        )

    return {
        "improved": sorted(comparisons, key=lambda item: item["delta"], reverse=True)[:5],
        "regressed": sorted(comparisons, key=lambda item: item["delta"])[:5],
    }


def classify_case_change(hash_case: dict, bge_case: dict, delta: float) -> str:
    hash_pollution = hash_case["metrics"].get("context_pollution_rate", 0)
    bge_pollution = bge_case["metrics"].get("context_pollution_rate", 0)
    hash_no_hit = hash_case["metrics"].get("no_hit_correct")
    bge_no_hit = bge_case["metrics"].get("no_hit_correct")

    if hash_no_hit is True and bge_no_hit is False:
        return "new_false_positive"
    if bge_pollution < hash_pollution:
        return "cross_domain_confusion_reduced"
    if delta > 0.05:
        return "semantic_match_improved"
    if delta < -0.05:
        return "ranking_regression"
    if hash_case["metrics"].get("failure_reason") != bge_case["metrics"].get("failure_reason"):
        return "threshold_interaction"
    return "no_material_change"


def build_markdown_report(result: dict) -> str:
    lines = [
        "# CrisisAgent Embedding Ablation - Hash vs BGE",
        "",
        "## Experiment",
        "",
        f"- split: `{result['split']}`",
        "- BGE model: `BAAI/bge-small-zh`",
        "- BGE fallback to Hash: `False`",
        "- Final Set run: `False`",
        f"- top_k: `{result['top_k']}`",
        f"- min_rerank_score: `{result['min_rerank_score']}`",
        "- Fixed variables: Knowledge Base V2, cases, query rewrite, chunking, KeywordRetriever, VectorStore, HybridRetriever weights, RuleBasedReranker, threshold.",
        "",
        "## Overall Comparison",
        "",
        "| Metric | Hash | BGE | Absolute Difference | Relative Difference |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric, values in result["comparison"].items():
        lines.append(
            f"| {metric} | {values['hash']} | {values['bge']} | "
            f"{values['absolute_difference']} | {values['relative_difference']} |"
        )

    lines.extend(["", "## Performance", ""])
    for model_key in ("hash", "bge"):
        model_result = result[model_key]
        lines.extend(
            [
                f"### {model_key}",
                "",
                f"- model_initialization_ms: `{model_result['model_initialization_ms']}`",
                f"- query_embedding_latency_ms: `{model_result['performance']['query_embedding_latency_ms']}`",
                f"- total_retrieval_latency_ms: `{model_result['performance']['total_retrieval_latency_ms']}`",
                f"- query_embedding_call_count: `{model_result['performance']['query_embedding_call_count']}`",
                "",
            ]
        )

    lines.extend(["## Category Comparison", ""])
    categories = sorted(result["hash"]["categories"])
    for category in categories:
        lines.extend([f"### {category}", ""])
        hash_metrics = result["hash"]["categories"][category]
        bge_metrics = result["bge"]["categories"][category]
        for metric in ("recall_at_3", "mrr", "no_hit_accuracy", "source_category_match", "context_pollution_rate"):
            lines.append(f"- {metric}: Hash `{hash_metrics[metric]}` | BGE `{bge_metrics[metric]}`")
        lines.append("")

    lines.extend(["## Biggest Improvements", ""])
    lines.extend(_case_lines(result["case_comparison"]["improved"]))
    lines.extend(["", "## Biggest Regressions", ""])
    lines.extend(_case_lines(result["case_comparison"]["regressed"]))
    return "\n".join(lines)


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def summarize_latencies(values: list[float]) -> dict:
    if not values:
        return {"average": 0.0, "p50": 0.0, "p95": 0.0}
    sorted_values = sorted(values)
    return {
        "average": round(sum(values) / len(values), 2),
        "p50": round(statistics.median(sorted_values), 2),
        "p95": round(_percentile(sorted_values, 0.95), 2),
    }


def _case_quality_score(case: dict) -> float:
    metrics = case["metrics"]
    if case.get("expected_hit"):
        return (
            (metrics.get("recall_at_3") or 0)
            + (metrics.get("reciprocal_rank") or 0)
            - metrics.get("context_pollution_rate", 0)
        )
    return 1.0 if metrics.get("no_hit_correct") else -1.0


def _case_trace(case: dict) -> dict:
    return {
        "vector_top_results": [
            {
                "source": source.get("source"),
                "score": source.get("score"),
            }
            for source in case["vector_top_results"]
        ],
        "final_sources": case["metrics"].get("retrieved_sources", []),
        "scores": case["metrics"].get("scores", []),
        "rerank_scores": case["metrics"].get("rerank_scores", []),
        "failure_reason": case["metrics"].get("failure_reason"),
    }


def _case_lines(cases: list[dict]) -> list[str]:
    lines = []
    for case in cases:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- category: `{case['category']}`",
                f"- query: `{case['query']}`",
                f"- delta: `{case['delta']}`",
                f"- reason: `{case['reason']}`",
                f"- Hash vector top results: `{case['hash']['vector_top_results']}`",
                f"- Hash final sources: `{case['hash']['final_sources']}`",
                f"- Hash rerank scores: `{case['hash']['rerank_scores']}`",
                f"- BGE vector top results: `{case['bge']['vector_top_results']}`",
                f"- BGE final sources: `{case['bge']['final_sources']}`",
                f"- BGE rerank scores: `{case['bge']['rerank_scores']}`",
                "",
            ]
        )
    return lines


def _diff(hash_value: float, bge_value: float) -> dict:
    absolute = round(bge_value - hash_value, 4)
    relative = "N/A" if hash_value == 0 else round(absolute / hash_value, 4)
    return {
        "hash": hash_value,
        "bge": bge_value,
        "absolute_difference": absolute,
        "relative_difference": relative,
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


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HashEmbedding vs BGEEmbedding development ablation.")
    parser.add_argument("--split", default="development", choices=["development"])
    args = parser.parse_args()

    try:
        result = run_ablation(split=args.split)
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

    report_path = save_report(result)
    printable = {
        "status": "OK",
        "report_path": str(report_path),
        "hash_summary": result["hash"]["summary"],
        "bge_summary": result["bge"]["summary"],
        "comparison": result["comparison"],
        "hash_performance": result["hash"]["performance"],
        "bge_performance": result["bge"]["performance"],
        "bge_initialization_ms": result["bge"]["model_initialization_ms"],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
