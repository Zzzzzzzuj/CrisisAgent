import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.reranker import RuleBasedReranker
from backend.rag.retrieval_need_gate import evaluate_retrieval_need
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_retriever import VectorRetriever
from evaluation.bge_threshold_calibration import NEGATIVE_CASES_PATH, TOP_K, load_negative_cases
from evaluation.rag_evaluator_v2 import DEFAULT_CASES_PATH, load_cases
from evaluation.rag_metrics_v2 import evaluate_retrieval_case, summarize_subset


REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_rag_gate_development.md"
MIN_RERANK_SCORE = 0.1


class DisabledFallbackRetriever:
    def retrieve(self, query: str, top_k: int = TOP_K) -> RetrievalResult:
        raise RuntimeError("Fallback is disabled for RAG gate evaluation.")


def load_positive_development_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return [
        case
        for case in load_cases(cases_path)
        if case.get("split") == "development" and case.get("expected_hit", True)
    ]


def run_gate_evaluation(
    positive_cases_path: str | Path = DEFAULT_CASES_PATH,
    negative_cases_path: str | Path = NEGATIVE_CASES_PATH,
    retriever=None,
) -> dict:
    positive_cases = load_positive_development_cases(positive_cases_path)
    negative_cases = _normalize_negative_cases(load_negative_cases(negative_cases_path))
    all_cases = positive_cases + negative_cases
    active_retriever = retriever or build_bge_pipeline()

    without_gate_results = [
        evaluate_case_with_retrieval(case, active_retriever, gate_result=None)
        for case in all_cases
    ]
    with_gate_results = [
        evaluate_case_with_gate(case, active_retriever)
        for case in all_cases
    ]
    gate_summary = summarize_gate_results(with_gate_results)

    return {
        "experiment": "Retrieval Need Gate Development Evaluation",
        "split": "development",
        "old_final_run": False,
        "positive_case_count": len(positive_cases),
        "negative_case_count": len(negative_cases),
        "negative_type_counts": _count_by_field(negative_cases, "type"),
        "gate": gate_summary,
        "without_gate": summarize_end_to_end(without_gate_results),
        "with_gate": summarize_end_to_end(with_gate_results),
        "false_positives": _select_gate_cases(with_gate_results, "FP"),
        "false_negatives": _select_gate_cases(with_gate_results, "FN"),
        "case_results": with_gate_results,
    }


def build_bge_pipeline() -> RagPipelineRetriever:
    bge_model = BGEEmbeddingModel()
    vector_retriever = VectorRetriever(embedding_model=bge_model)
    return RagPipelineRetriever(
        hybrid_retriever=HybridRetriever(
            keyword_retriever=KeywordRetriever(),
            vector_retriever=vector_retriever,
        ),
        reranker=RuleBasedReranker(),
        fallback_retriever=DisabledFallbackRetriever(),
        min_rerank_score=MIN_RERANK_SCORE,
    )


def evaluate_case_with_gate(case: dict, retriever) -> dict:
    gate_result = evaluate_retrieval_need(
        event=case["query"],
        draft=case.get("draft", ""),
        redteam_review=case.get("redteam_review"),
    )
    if not gate_result["need_rag"]:
        retrieval = empty_retrieval_result()
    else:
        retrieval = retriever.retrieve(case["query"], top_k=TOP_K).to_dict()
    return _build_case_result(case, retrieval, gate_result)


def evaluate_case_with_retrieval(case: dict, retriever, gate_result: dict | None) -> dict:
    retrieval = retriever.retrieve(case["query"], top_k=TOP_K).to_dict()
    return _build_case_result(case, retrieval, gate_result)


def empty_retrieval_result() -> dict:
    return {
        "context": "",
        "chunks": [],
        "sources": [],
    }


def summarize_gate_results(case_results: list[dict]) -> dict:
    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for case in case_results:
        counts[case["gate_label"]] += 1

    negative_cases = [case for case in case_results if not case.get("expected_hit")]
    return {
        **counts,
        "tpr": _safe_rate(counts["TP"], counts["TP"] + counts["FN"]),
        "tnr": _safe_rate(counts["TN"], counts["TN"] + counts["FP"]),
        "fpr": _safe_rate(counts["FP"], counts["FP"] + counts["TN"]),
        "fnr": _safe_rate(counts["FN"], counts["FN"] + counts["TP"]),
        "accuracy": _safe_rate(counts["TP"] + counts["TN"], len(case_results)),
        "hard_negative_reject_rate": _reject_rate(negative_cases, "hard_negative"),
        "business_non_crisis_reject_rate": _reject_rate(negative_cases, "business_non_crisis"),
        "unrelated_reject_rate": _reject_rate(negative_cases, "unrelated"),
    }


def summarize_end_to_end(case_results: list[dict]) -> dict:
    positive_results = [case for case in case_results if case.get("expected_hit")]
    negative_results = [case for case in case_results if not case.get("expected_hit")]
    positive_summary = summarize_subset(positive_results)
    negative_summary = summarize_subset(negative_results)

    return {
        "total_cases": len(case_results),
        "positive_case_count": len(positive_results),
        "negative_case_count": len(negative_results),
        "recall_at_1": positive_summary["recall_at_1"],
        "recall_at_3": positive_summary["recall_at_3"],
        "recall_at_5": positive_summary["recall_at_5"],
        "mrr": positive_summary["mrr"],
        "no_hit_accuracy": negative_summary["no_hit_accuracy"],
        "context_pollution_rate": positive_summary["context_pollution_rate"],
        "fallback_count": positive_summary["fallback_count"] + negative_summary["fallback_count"],
    }


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def build_markdown_report(result: dict) -> str:
    gate = result["gate"]
    without_gate = result["without_gate"]
    with_gate = result["with_gate"]
    lines = [
        "# CrisisAgent RAG Gate Development Evaluation",
        "",
        "## Experiment",
        "",
        "- Gate type: `deterministic_retrieval_need_gate`",
        "- Production Legal Agent path changed: `False`",
        "- Old Final Set run: `False`",
        "- BGE model: `BAAI/bge-small-zh`",
        f"- min_rerank_score: `{MIN_RERANK_SCORE}`",
        f"- positive cases: `{result['positive_case_count']}`",
        f"- negative cases: `{result['negative_case_count']}`",
        f"- negative type counts: `{result['negative_type_counts']}`",
        "- scope: These are Development + Calibration results, not final generalization results.",
        "- calibration note: The 24 negative cases were used during Retrieval Need Gate development analysis.",
        "- challenge set requirement: The next step must validate this Gate on an untouched Challenge Set.",
        "- production note: The Gate has not been integrated into the Legal Agent production path.",
        "- metric note: Phase 3D Context Pollution Rate uses a different evaluation scope than Phase 3C, so do not compute a direct improvement ratio between them.",
        "",
        "## Gate Metrics",
        "",
        f"- TP: `{gate['TP']}`",
        f"- TN: `{gate['TN']}`",
        f"- FP: `{gate['FP']}`",
        f"- FN: `{gate['FN']}`",
        f"- TPR / Recall: `{gate['tpr']}`",
        f"- TNR / Specificity: `{gate['tnr']}`",
        f"- FPR: `{gate['fpr']}`",
        f"- FNR: `{gate['fnr']}`",
        f"- Accuracy: `{gate['accuracy']}`",
        f"- hard_negative_reject_rate: `{gate['hard_negative_reject_rate']}`",
        f"- business_non_crisis_reject_rate: `{gate['business_non_crisis_reject_rate']}`",
        f"- unrelated_reject_rate: `{gate['unrelated_reject_rate']}`",
        "",
        "## End-to-End Comparison",
        "",
        "| Metric | BGE without Gate | BGE + Gate |",
        "|---|---:|---:|",
        f"| Recall@3 | {without_gate['recall_at_3']} | {with_gate['recall_at_3']} |",
        f"| MRR | {without_gate['mrr']} | {with_gate['mrr']} |",
        f"| No-hit Accuracy | {without_gate['no_hit_accuracy']} | {with_gate['no_hit_accuracy']} |",
        f"| Context Pollution Rate | {without_gate['context_pollution_rate']} | {with_gate['context_pollution_rate']} |",
        "",
        "## False Positives",
        "",
    ]
    lines.extend(_case_lines(result["false_positives"]))
    lines.extend(["", "## False Negatives", ""])
    lines.extend(_case_lines(result["false_negatives"]))
    return "\n".join(lines)


def _build_case_result(case: dict, retrieval: dict, gate_result: dict | None) -> dict:
    metrics = evaluate_retrieval_case(case, retrieval)
    expected_hit = bool(case.get("expected_hit", True))
    need_rag = bool(gate_result["need_rag"]) if gate_result else True
    return {
        "id": case["id"],
        "split": case.get("split", "calibration"),
        "category": case.get("category", case.get("type", "unknown")),
        "type": case.get("type"),
        "query": case["query"],
        "acceptable_sources": case.get("acceptable_sources", []),
        "expected_hit": expected_hit,
        "forbidden_sources": case.get("forbidden_sources", []),
        "forbidden_categories": case.get("forbidden_categories", []),
        "retrieval": retrieval,
        "metrics": metrics,
        "gate": gate_result,
        "gate_label": _gate_label(expected_hit, need_rag),
    }


def _gate_label(expected_hit: bool, need_rag: bool) -> str:
    if expected_hit and need_rag:
        return "TP"
    if expected_hit and not need_rag:
        return "FN"
    if not expected_hit and need_rag:
        return "FP"
    return "TN"


def _normalize_negative_cases(cases: list[dict]) -> list[dict]:
    return [
        {
            **case,
            "split": "development",
            "category": case.get("type", "negative"),
            "acceptable_sources": [],
            "forbidden_sources": [],
            "forbidden_categories": [],
        }
        for case in cases
    ]


def _select_gate_cases(case_results: list[dict], label: str) -> list[dict]:
    selected = []
    for case in case_results:
        if case["gate_label"] != label:
            continue
        selected.append(
            {
                "case_id": case["id"],
                "category": case["category"],
                "query": case["query"],
                "intent": case["gate"]["intent"] if case.get("gate") else None,
                "decision_score": case["gate"]["decision_score"] if case.get("gate") else None,
                "reason": case["gate"]["reason"] if case.get("gate") else None,
                "matched_signals": case["gate"]["matched_signals"] if case.get("gate") else [],
                "negative_signals": case["gate"]["negative_signals"] if case.get("gate") else [],
            }
        )
    return selected


def _reject_rate(case_results: list[dict], case_type: str) -> float:
    cases = [case for case in case_results if case.get("type") == case_type]
    if not cases:
        return 0.0
    rejected = sum(1 for case in cases if case["gate_label"] == "TN")
    return _safe_rate(rejected, len(cases))


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _count_by_field(cases: list[dict], field: str) -> dict:
    counts: dict[str, int] = {}
    for case in cases:
        value = str(case.get(field, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _case_lines(cases: list[dict]) -> list[str]:
    if not cases:
        return ["- None"]
    lines = []
    for case in cases:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- category: `{case['category']}`",
                f"- query: {case['query']}",
                f"- intent: `{case['intent']}`",
                f"- decision_score: `{case['decision_score']}`",
                f"- matched_signals: `{case['matched_signals']}`",
                f"- negative_signals: `{case['negative_signals']}`",
                f"- reason: {case['reason']}",
                "",
            ]
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Retrieval Need Gate development evaluation.")
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args()

    try:
        result = run_gate_evaluation()
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
        "gate": result["gate"],
        "without_gate": {
            "recall_at_3": result["without_gate"]["recall_at_3"],
            "mrr": result["without_gate"]["mrr"],
            "no_hit_accuracy": result["without_gate"]["no_hit_accuracy"],
            "context_pollution_rate": result["without_gate"]["context_pollution_rate"],
        },
        "with_gate": {
            "recall_at_3": result["with_gate"]["recall_at_3"],
            "mrr": result["with_gate"]["mrr"],
            "no_hit_accuracy": result["with_gate"]["no_hit_accuracy"],
            "context_pollution_rate": result["with_gate"]["context_pollution_rate"],
        },
        "false_positives": result["false_positives"],
        "false_negatives": result["false_negatives"],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
