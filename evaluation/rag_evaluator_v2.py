import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.retriever import retrieve
from evaluation.rag_metrics_v2 import K_VALUES, evaluate_retrieval_case, summarize_rag_results


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALUATION_DIR / "rag_cases_v2.json"
OUTPUTS_DIR = EVALUATION_DIR / "outputs"
REPORTS_DIR = EVALUATION_DIR / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "latest_rag_report_v2_baseline.md"


def load_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(cases_path).read_text(encoding="utf-8"))


def evaluate_case(case: dict, top_k: int = 5) -> dict:
    retrieval = retrieve(case["query"], top_k=top_k)
    metrics = evaluate_retrieval_case(case, retrieval)
    return {
        "id": case["id"],
        "split": case["split"],
        "category": case["category"],
        "query": case["query"],
        "acceptable_sources": case.get("acceptable_sources", []),
        "expected_hit": case.get("expected_hit", True),
        "forbidden_sources": case.get("forbidden_sources", []),
        "forbidden_categories": case.get("forbidden_categories", []),
        "retrieval": retrieval,
        "metrics": metrics,
    }


def evaluate_cases(cases_path: str | Path = DEFAULT_CASES_PATH, top_k: int = 5) -> dict:
    cases = load_cases(cases_path)
    _validate_cases(cases)
    case_results = [evaluate_case(case, top_k=top_k) for case in cases]
    summary = summarize_rag_results(case_results)
    summary["retrieval_baseline"] = {
        "retriever": "current_default_pipeline",
        "keyword_retriever": True,
        "vector_retriever": True,
        "embedding": "HashEmbeddingModel",
        "hybrid_retrieval": True,
        "reranker": "RuleBasedReranker",
        "min_rerank_score": 0.1,
        "top_k": top_k,
    }
    summary["case_results"] = case_results
    return summary


def save_results(
    summary: dict,
    outputs_dir: str | Path = OUTPUTS_DIR,
    reports_dir: str | Path = REPORTS_DIR,
) -> dict:
    outputs_path = Path(outputs_dir)
    reports_path = Path(reports_dir)
    outputs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = outputs_path / f"rag-evaluation-v2-baseline-{timestamp}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = reports_path / LATEST_REPORT_PATH.name
    markdown_path.write_text(build_markdown_report(summary), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_markdown_report(summary: dict) -> str:
    baseline = summary["retrieval_baseline"]
    lines = [
        "# CrisisAgent RAG Evaluation V2 Baseline",
        "",
        "## Baseline Configuration",
        "",
        f"- Retriever: `{baseline['retriever']}`",
        f"- Hybrid retrieval: `{baseline['hybrid_retrieval']}`",
        f"- Embedding: `{baseline['embedding']}`",
        f"- Reranker: `{baseline['reranker']}`",
        f"- min_rerank_score: `{baseline['min_rerank_score']}`",
        f"- top_k: `{baseline['top_k']}`",
        "",
        "## Overall Metrics",
        "",
    ]
    lines.extend(_metric_lines(summary["overall"]))
    lines.extend(["", "## Split Metrics", ""])
    for split, metrics in summary["splits"].items():
        lines.extend([f"### {split}", ""])
        lines.extend(_metric_lines(metrics))
        lines.append("")

    lines.extend(["## Category Metrics", ""])
    for category, metrics in summary["categories"].items():
        lines.extend([f"### {category}", ""])
        lines.extend(_metric_lines(metrics))
        lines.append("")

    lines.extend(["## Worst Cases", ""])
    for case in summary["worst_cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- Category: `{case['category']}`",
                f"- Query: {case['query']}",
                f"- Acceptable sources: `{', '.join(case['acceptable_sources'])}`",
                f"- Actual sources: `{', '.join(case['actual_sources'])}`",
                f"- Scores: `{case['scores']}`",
                f"- Rerank scores: `{case['rerank_scores']}`",
                f"- Retrieval type: `{case['retrieval_type']}`",
                f"- Fallback used: `{case['fallback_used']}`",
                f"- Failure reason: `{case['failure_reason']}`",
                "",
            ]
        )
    return "\n".join(lines)


def _metric_lines(metrics: dict) -> list[str]:
    return [
        f"- Total cases: `{metrics['total_cases']}`",
        f"- Hit case count: `{metrics['hit_case_count']}`",
        f"- No-hit case count: `{metrics['no_hit_case_count']}`",
        f"- Recall@1: `{metrics['recall_at_1']}`",
        f"- Recall@3: `{metrics['recall_at_3']}`",
        f"- Recall@5: `{metrics['recall_at_5']}`",
        f"- Precision@1: `{metrics['precision_at_1']}`",
        f"- Precision@3: `{metrics['precision_at_3']}`",
        f"- Precision@5: `{metrics['precision_at_5']}`",
        f"- MRR: `{metrics['mrr']}`",
        f"- No-hit Accuracy: `{metrics['no_hit_accuracy']}`",
        f"- Source Category Match: `{metrics['source_category_match']}`",
        f"- Context Pollution Rate: `{metrics['context_pollution_rate']}`",
        f"- Fallback count: `{metrics['fallback_count']}`",
    ]


def _validate_cases(cases: list[dict]) -> None:
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("rag_cases_v2 contains duplicate case ids.")
    development_ids = {case["id"] for case in cases if case.get("split") == "development"}
    final_ids = {case["id"] for case in cases if case.get("split") == "final"}
    if development_ids & final_ids:
        raise ValueError("development and final case ids must not overlap.")


def main() -> None:
    summary = evaluate_cases()
    saved_paths = save_results(summary)
    print(
        json.dumps(
            {
                "summary": {
                    key: value
                    for key, value in summary.items()
                    if key != "case_results"
                },
                "saved_paths": saved_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
