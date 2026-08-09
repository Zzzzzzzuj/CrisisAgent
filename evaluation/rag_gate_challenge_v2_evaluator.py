import argparse
import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.reranker import RuleBasedReranker
from backend.rag.retrieval_need_gate import evaluate_retrieval_need
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_retriever import VectorRetriever
from evaluation.rag_metrics_v2 import evaluate_retrieval_case, summarize_subset


CHALLENGE_PATH = PROJECT_ROOT / "evaluation" / "rag_gate_challenge_v2.json"
PROTOCOL_PATH = PROJECT_ROOT / "evaluation" / "reports" / "rag_gate_challenge_v2_protocol.md"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_rag_gate_challenge_v2.md"

TOP_K = 5
MIN_RERANK_SCORE = 0.1
BGE_MODEL_NAME = "BAAI/bge-small-zh"

ACCEPTABLE_SOURCES_BY_CATEGORY = {
    "food_safety": ["food_safety.md"],
    "data_privacy": ["data_privacy.md"],
    "service_outage": ["service_outage.md"],
    "product_quality": ["product_quality.md"],
    "executive_misconduct": ["executive_misconduct.md"],
}
DOMAIN_SOURCES = set().union(*ACCEPTABLE_SOURCES_BY_CATEGORY.values())
POSITIVE_CATEGORIES = tuple(ACCEPTABLE_SOURCES_BY_CATEGORY)
NEGATIVE_TYPES = {
    "unrelated": 4,
    "business_non_crisis": 4,
    "hard_negative": 12,
}
ACCEPTANCE_CRITERIA = {
    "positive_tpr": 0.90,
    "negative_tnr": 0.85,
    "hard_negative_reject_rate": 0.75,
    "max_false_negatives": 2,
    "hard_negative_reject_count": 9,
    "min_positive_category_tpr": 0.75,
    "recall_at_3": 0.63,
    "no_hit_accuracy": 0.85,
}


class DisabledFallbackRetriever:
    def retrieve(self, query: str, top_k: int = TOP_K) -> RetrievalResult:
        raise RuntimeError("Fallback is disabled for Challenge v2 Evaluation.")


def load_challenge_cases(path: str | Path = CHALLENGE_PATH, validate_dataset: bool = True) -> list[dict]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if validate_dataset:
        validate_challenge_cases(cases)
    return cases


def validate_challenge_cases(cases: list[dict]) -> None:
    ids = [case.get("id") for case in cases]
    if len(cases) != 40:
        raise ValueError(f"Challenge v2 must contain 40 cases, got {len(cases)}.")
    if len(ids) != len(set(ids)):
        raise ValueError("Challenge v2 contains duplicate ids.")

    positives = [case for case in cases if case.get("label") == "need_rag"]
    negatives = [case for case in cases if case.get("label") == "no_rag"]
    if len(positives) != 20 or len(negatives) != 20:
        raise ValueError("Challenge v2 must contain 20 positive and 20 negative cases.")

    expected_positive_counts = {category: 4 for category in POSITIVE_CATEGORIES}
    positive_counts = _count_by_field(positives, "category")
    if positive_counts != expected_positive_counts:
        raise ValueError(f"Unexpected positive distribution: {positive_counts}.")

    negative_counts = _count_by_field(negatives, "type")
    if negative_counts != NEGATIVE_TYPES:
        raise ValueError(f"Unexpected negative distribution: {negative_counts}.")

    for case in cases:
        for field in ("id", "label", "type", "category", "event", "notes"):
            if field not in case:
                raise ValueError(f"Case {case.get('id')} is missing {field}.")


def build_bge_pipeline() -> RagPipelineRetriever:
    from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

    bge_model = BGEEmbeddingModel(model_name=BGE_MODEL_NAME)
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


def run_challenge_evaluation(
    challenge_path: str | Path = CHALLENGE_PATH,
    retriever=None,
    gate_fn: Callable[..., dict] = evaluate_retrieval_need,
    validate_dataset: bool = True,
) -> dict:
    cases = load_challenge_cases(challenge_path, validate_dataset=validate_dataset)
    active_retriever = retriever or build_bge_pipeline()
    case_results = [evaluate_challenge_case(case, active_retriever, gate_fn) for case in cases]
    gate_summary = summarize_gate_results(case_results)
    end_to_end_summary = summarize_end_to_end(case_results)
    acceptance = evaluate_acceptance(gate_summary, end_to_end_summary)

    return {
        "experiment": "Retrieval Need Gate v2 Challenge v2 First Evaluation",
        "dataset": str(CHALLENGE_PATH.relative_to(PROJECT_ROOT)),
        "protocol": str(PROTOCOL_PATH.relative_to(PROJECT_ROOT)),
        "challenge_frozen_commit": _git_last_commit(CHALLENGE_PATH),
        "protocol_frozen_commit": _git_last_commit(PROTOCOL_PATH),
        "gate_v2_commit": _git_last_commit(PROJECT_ROOT / "backend" / "rag" / "retrieval_need_gate.py"),
        "evaluation_base_commit": _git_head(),
        "python_executable": sys.executable,
        "sentence_transformers_version": _package_version("sentence-transformers"),
        "bge_model": BGE_MODEL_NAME,
        "bge_fallback_used": False,
        "split": "challenge_v2",
        "total_cases": len(cases),
        "positive_case_count": sum(1 for case in cases if case["label"] == "need_rag"),
        "negative_case_count": sum(1 for case in cases if case["label"] == "no_rag"),
        "positive_category_counts": _count_by_field(
            [case for case in cases if case["label"] == "need_rag"],
            "category",
        ),
        "negative_type_counts": _count_by_field(
            [case for case in cases if case["label"] == "no_rag"],
            "type",
        ),
        "gate": gate_summary,
        "end_to_end": end_to_end_summary,
        "acceptance": acceptance,
        "false_positives": _select_gate_cases(case_results, "FP"),
        "false_negatives": _select_gate_cases(case_results, "FN"),
        "failure_cases": _select_failure_cases(case_results),
        "case_results": case_results,
    }


def evaluate_challenge_case(case: dict, retriever, gate_fn: Callable[..., dict]) -> dict:
    gate_result = predict_gate(case, gate_fn)
    normalized_case = normalize_case_for_retrieval(case)

    if not gate_result["need_rag"]:
        retrieval = empty_retrieval_result()
    else:
        retrieval = retriever.retrieve(case["event"], top_k=TOP_K).to_dict()

    metrics = evaluate_retrieval_case(normalized_case, retrieval)
    expected_need = case["label"] == "need_rag"
    gate_label = _gate_label(expected_need, bool(gate_result["need_rag"]))

    return {
        **case,
        **normalized_case,
        "gate": gate_result,
        "gate_label": gate_label,
        "retrieval": retrieval,
        "metrics": metrics,
        "failure_reason": classify_challenge_failure(gate_label, metrics),
    }


def predict_gate(case: dict, gate_fn: Callable[..., dict] = evaluate_retrieval_need) -> dict:
    return gate_fn(event=case["event"])


def normalize_case_for_retrieval(case: dict) -> dict:
    expected_hit = case["label"] == "need_rag"
    acceptable_sources = ACCEPTABLE_SOURCES_BY_CATEGORY.get(case["category"], []) if expected_hit else []
    forbidden_sources = sorted(DOMAIN_SOURCES - set(acceptable_sources))

    return {
        "id": case["id"],
        "split": "challenge_v2",
        "category": case["category"],
        "type": case["type"],
        "query": case["event"],
        "expected_hit": expected_hit,
        "acceptable_sources": acceptable_sources,
        "forbidden_sources": forbidden_sources,
        "forbidden_categories": [],
    }


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

    positive_cases = [case for case in case_results if case["label"] == "need_rag"]
    negative_cases = [case for case in case_results if case["label"] == "no_rag"]
    positive_by_category = {
        category: _positive_pass_rate(
            [case for case in positive_cases if case["category"] == category]
        )
        for category in POSITIVE_CATEGORIES
    }
    negative_by_type = {
        case_type: _negative_reject_rate(
            [case for case in negative_cases if case["type"] == case_type]
        )
        for case_type in NEGATIVE_TYPES
    }
    negative_reject_counts = {
        case_type: _negative_reject_count(
            [case for case in negative_cases if case["type"] == case_type]
        )
        for case_type in NEGATIVE_TYPES
    }

    return {
        **counts,
        "tpr": _safe_rate(counts["TP"], counts["TP"] + counts["FN"]),
        "tnr": _safe_rate(counts["TN"], counts["TN"] + counts["FP"]),
        "fpr": _safe_rate(counts["FP"], counts["FP"] + counts["TN"]),
        "fnr": _safe_rate(counts["FN"], counts["FN"] + counts["TP"]),
        "accuracy": _safe_rate(counts["TP"] + counts["TN"], len(case_results)),
        "hard_negative_reject_rate": negative_by_type.get("hard_negative", 0.0),
        "hard_negative_reject_count": negative_reject_counts.get("hard_negative", 0),
        "positive_by_category": positive_by_category,
        "negative_by_type": negative_by_type,
        "negative_reject_counts": negative_reject_counts,
    }


def summarize_end_to_end(case_results: list[dict]) -> dict:
    positive_results = [case for case in case_results if case["expected_hit"]]
    negative_results = [case for case in case_results if not case["expected_hit"]]
    positive_summary = summarize_subset(positive_results)
    negative_summary = summarize_subset(negative_results)
    all_summary = summarize_subset(case_results)
    negative_type_metrics = _summarize_by_field(negative_results, "type")

    return {
        "total_cases": len(case_results),
        "positive_case_count": len(positive_results),
        "negative_case_count": len(negative_results),
        "recall_at_1": positive_summary["recall_at_1"],
        "recall_at_3": positive_summary["recall_at_3"],
        "recall_at_5": positive_summary["recall_at_5"],
        "precision_at_1": all_summary["precision_at_1"],
        "precision_at_3": all_summary["precision_at_3"],
        "precision_at_5": all_summary["precision_at_5"],
        "mrr": positive_summary["mrr"],
        "no_hit_accuracy": negative_summary["no_hit_accuracy"],
        "negative_no_hit_by_type": {
            case_type: metrics["no_hit_accuracy"]
            for case_type, metrics in negative_type_metrics.items()
        },
        "source_category_match": all_summary["source_category_match"],
        "context_pollution_rate": all_summary["context_pollution_rate"],
        "fallback_count": all_summary["fallback_count"],
        "gate_failure_count": sum(
            1 for case in case_results
            if case["failure_reason"] in {"gate_false_negative", "gate_false_positive"}
        ),
        "retrieval_failure_count": sum(
            1 for case in case_results
            if case["failure_reason"] not in {"none", "gate_false_negative", "gate_false_positive"}
        ),
        "category_metrics": _summarize_by_field(positive_results, "category"),
        "negative_type_metrics": negative_type_metrics,
    }


def evaluate_acceptance(gate_summary: dict, end_to_end_summary: dict) -> dict:
    category_checks = {
        category: tpr >= ACCEPTANCE_CRITERIA["min_positive_category_tpr"]
        for category, tpr in gate_summary["positive_by_category"].items()
    }
    checks = {
        "positive_tpr": gate_summary["tpr"] >= ACCEPTANCE_CRITERIA["positive_tpr"],
        "negative_tnr": gate_summary["tnr"] >= ACCEPTANCE_CRITERIA["negative_tnr"],
        "hard_negative_reject_rate": (
            gate_summary["hard_negative_reject_rate"]
            >= ACCEPTANCE_CRITERIA["hard_negative_reject_rate"]
        ),
        "false_negative_count": gate_summary["FN"] <= ACCEPTANCE_CRITERIA["max_false_negatives"],
        "hard_negative_reject_count": (
            gate_summary["hard_negative_reject_count"]
            >= ACCEPTANCE_CRITERIA["hard_negative_reject_count"]
        ),
        "positive_category_tpr": all(category_checks.values()),
        "recall_at_3": end_to_end_summary["recall_at_3"] >= ACCEPTANCE_CRITERIA["recall_at_3"],
        "no_hit_accuracy": (
            end_to_end_summary["no_hit_accuracy"]
            >= ACCEPTANCE_CRITERIA["no_hit_accuracy"]
        ),
    }
    return {
        "criteria": ACCEPTANCE_CRITERIA,
        "checks": checks,
        "category_checks": category_checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def classify_challenge_failure(gate_label: str, metrics: dict) -> str:
    if gate_label == "FN":
        return "gate_false_negative"
    if gate_label == "FP":
        return "gate_false_positive"
    if metrics.get("failure_reason") and metrics["failure_reason"] != "none":
        return metrics["failure_reason"]
    return "none"


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def build_markdown_report(result: dict) -> str:
    gate = result["gate"]
    end_to_end = result["end_to_end"]
    acceptance = result["acceptance"]
    lines = [
        "# CrisisAgent Retrieval Need Gate Challenge v2 Evaluation",
        "",
        "## Experiment Metadata",
        "",
        f"- experiment: `{result['experiment']}`",
        f"- dataset: `{result['dataset']}`",
        f"- protocol: `{result['protocol']}`",
        f"- challenge_frozen_commit: `{result['challenge_frozen_commit']}`",
        f"- protocol_frozen_commit: `{result['protocol_frozen_commit']}`",
        f"- gate_v2_commit: `{result['gate_v2_commit']}`",
        f"- evaluation_base_commit: `{result['evaluation_base_commit']}`",
        f"- python_executable: `{result['python_executable']}`",
        f"- sentence_transformers_version: `{result['sentence_transformers_version']}`",
        f"- bge_model: `{result['bge_model']}`",
        f"- bge_fallback_used: `{result['bge_fallback_used']}`",
        f"- top_k: `{TOP_K}`",
        f"- min_rerank_score: `{MIN_RERANK_SCORE}`",
        "- Challenge v2 status: `no longer untouched after this first formal evaluation`",
        "- Gate production input used in this evaluator: `event` only",
        "- Gate v1 Challenge v1 FIRST RUN: `TPR=0.20, TNR=1.00, Status=FAIL`",
        "- Gate v2 Challenge v1 result is only `post-hoc regression`, not independent validation.",
        "",
        "## Dataset",
        "",
        f"- total_cases: `{result['total_cases']}`",
        f"- positive_case_count: `{result['positive_case_count']}`",
        f"- negative_case_count: `{result['negative_case_count']}`",
        f"- positive_category_counts: `{result['positive_category_counts']}`",
        f"- negative_type_counts: `{result['negative_type_counts']}`",
        "",
        "## Pre-Registered Acceptance",
        "",
        f"- Positive TPR >= `{ACCEPTANCE_CRITERIA['positive_tpr']}`",
        f"- Negative TNR >= `{ACCEPTANCE_CRITERIA['negative_tnr']}`",
        f"- Hard Negative Reject Rate >= `{ACCEPTANCE_CRITERIA['hard_negative_reject_rate']}`",
        f"- Gate FN <= `{ACCEPTANCE_CRITERIA['max_false_negatives']} / 20`",
        f"- Hard Negative reject count >= `{ACCEPTANCE_CRITERIA['hard_negative_reject_count']} / 12`",
        f"- Each Positive category TPR >= `{ACCEPTANCE_CRITERIA['min_positive_category_tpr']}`",
        f"- BGE + Gate Recall@3 >= `{ACCEPTANCE_CRITERIA['recall_at_3']}`",
        f"- No-hit Accuracy >= `{ACCEPTANCE_CRITERIA['no_hit_accuracy']}`",
        "- Context Pollution Rate must be reported.",
        "",
        "## Gate Metrics",
        "",
        f"- TP: `{gate['TP']}`",
        f"- TN: `{gate['TN']}`",
        f"- FP: `{gate['FP']}`",
        f"- FN: `{gate['FN']}`",
        f"- TPR: `{gate['tpr']}`",
        f"- TNR: `{gate['tnr']}`",
        f"- FPR: `{gate['fpr']}`",
        f"- FNR: `{gate['fnr']}`",
        f"- Accuracy: `{gate['accuracy']}`",
        f"- Hard Negative Reject Rate: `{gate['hard_negative_reject_rate']}`",
        f"- Hard Negative Reject Count: `{gate['hard_negative_reject_count']} / 12`",
        f"- Positive by Category: `{gate['positive_by_category']}`",
        f"- Negative by Type: `{gate['negative_by_type']}`",
        f"- Negative Reject Counts: `{gate['negative_reject_counts']}`",
        "",
        "## End-to-End BGE + Gate Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall@1 | {end_to_end['recall_at_1']} |",
        f"| Recall@3 | {end_to_end['recall_at_3']} |",
        f"| Recall@5 | {end_to_end['recall_at_5']} |",
        f"| Precision@1 | {end_to_end['precision_at_1']} |",
        f"| Precision@3 | {end_to_end['precision_at_3']} |",
        f"| Precision@5 | {end_to_end['precision_at_5']} |",
        f"| MRR | {end_to_end['mrr']} |",
        f"| No-hit Accuracy | {end_to_end['no_hit_accuracy']} |",
        f"| Source Category Match | {end_to_end['source_category_match']} |",
        f"| Context Pollution Rate | {end_to_end['context_pollution_rate']} |",
        f"| Fallback Count | {end_to_end['fallback_count']} |",
        f"| Gate Failure Count | {end_to_end['gate_failure_count']} |",
        f"| Retrieval Failure Count | {end_to_end['retrieval_failure_count']} |",
        "",
        "### Negative No-hit by Type",
        "",
        f"- `{end_to_end['negative_no_hit_by_type']}`",
        "",
        "## Acceptance Result",
        "",
        f"- status: `{acceptance['status']}`",
        f"- checks: `{acceptance['checks']}`",
        f"- category_checks: `{acceptance['category_checks']}`",
        "",
        "## False Positives",
        "",
    ]
    lines.extend(_case_lines(result["false_positives"]))
    lines.extend(["", "## False Negatives", ""])
    lines.extend(_case_lines(result["false_negatives"]))
    lines.extend(["", "## Failure Cases", ""])
    lines.extend(_failure_case_lines(result["failure_cases"]))
    lines.extend(
        [
            "",
        "## Limitations",
        "",
        "- This is the first formal prediction run on Challenge v2.",
        "- Challenge v2 is no longer untouched after this report.",
        "- `Retrieval Failure Count` means evaluation-level wrong-category or context-pollution quality errors; it does not mean a retrieval exception, BGE fallback, or pipeline crash.",
        "- Challenge v2 overall status is `FAIL`; Positive TPR=`1.0` and Recall@3=`0.9` must not be described as overall success.",
        "- The dataset must not be edited and rerun as an independent holdout.",
        "- If Gate changes are made later, a new Challenge v3 or another untouched holdout is required.",
    ]
    )
    return "\n".join(lines)


def _gate_label(expected_need: bool, need_rag: bool) -> str:
    if expected_need and need_rag:
        return "TP"
    if expected_need and not need_rag:
        return "FN"
    if not expected_need and need_rag:
        return "FP"
    return "TN"


def _positive_pass_rate(cases: list[dict]) -> float:
    if not cases:
        return 0.0
    passed = sum(1 for case in cases if case["gate_label"] == "TP")
    return _safe_rate(passed, len(cases))


def _negative_reject_rate(cases: list[dict]) -> float:
    if not cases:
        return 0.0
    rejected = _negative_reject_count(cases)
    return _safe_rate(rejected, len(cases))


def _negative_reject_count(cases: list[dict]) -> int:
    return sum(1 for case in cases if case["gate_label"] == "TN")


def _select_gate_cases(case_results: list[dict], label: str) -> list[dict]:
    return [
        _gate_case_summary(case)
        for case in case_results
        if case["gate_label"] == label
    ]


def _select_failure_cases(case_results: list[dict]) -> list[dict]:
    return [
        _failure_case_summary(case)
        for case in case_results
        if case["failure_reason"] != "none"
    ]


def _gate_case_summary(case: dict) -> dict:
    gate = case["gate"]
    return {
        "case_id": case["id"],
        "label": case["label"],
        "type": case["type"],
        "category": case["category"],
        "event": case["event"],
        "expected_label": case["label"],
        "predicted_need_rag": gate["need_rag"],
        "intent": gate["intent"],
        "decision_score": gate["decision_score"],
        "matched_signals": gate["matched_signals"],
        "negative_signals": gate["negative_signals"],
        "reason": gate["reason"],
    }


def _failure_case_summary(case: dict) -> dict:
    metrics = case["metrics"]
    return {
        **_gate_case_summary(case),
        "failure_reason": case["failure_reason"],
        "acceptable_sources": case["acceptable_sources"],
        "actual_sources": metrics["retrieved_sources"],
        "scores": metrics["scores"],
        "rerank_scores": metrics["rerank_scores"],
        "context_pollution_rate": metrics["context_pollution_rate"],
    }


def _case_lines(cases: list[dict]) -> list[str]:
    if not cases:
        return ["- None"]
    lines = []
    for case in cases:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- type: `{case['type']}`",
                f"- category: `{case['category']}`",
                f"- event: {case['event']}",
                f"- expected label: `{case['expected_label']}`",
                f"- predicted need_rag: `{case['predicted_need_rag']}`",
                f"- intent: `{case['intent']}`",
                f"- decision_score: `{case['decision_score']}`",
                f"- matched_signals: `{case['matched_signals']}`",
                f"- negative_signals: `{case['negative_signals']}`",
                f"- reason: {case['reason']}",
                "",
            ]
        )
    return lines


def _failure_case_lines(cases: list[dict]) -> list[str]:
    if not cases:
        return ["- None"]
    lines = []
    for case in cases:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- failure_reason: `{case['failure_reason']}`",
                f"- type: `{case['type']}`",
                f"- category: `{case['category']}`",
                f"- event: {case['event']}",
                f"- acceptable_sources: `{case['acceptable_sources']}`",
                f"- actual_sources: `{case['actual_sources']}`",
                f"- scores: `{case['scores']}`",
                f"- rerank_scores: `{case['rerank_scores']}`",
                f"- context_pollution_rate: `{case['context_pollution_rate']}`",
                f"- intent: `{case['intent']}`",
                f"- decision_score: `{case['decision_score']}`",
                "",
            ]
        )
    return lines


def _summarize_by_field(case_results: list[dict], field: str) -> dict:
    grouped: dict[str, list[dict]] = {}
    for case in case_results:
        grouped.setdefault(str(case.get(field, "unknown")), []).append(case)
    return {
        name: summarize_subset(items)
        for name, items in sorted(grouped.items())
    }


def _count_by_field(cases: list[dict], field: str) -> dict:
    counts: dict[str, int] = {}
    for case in cases:
        value = str(case.get(field, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


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
    parser = argparse.ArgumentParser(description="Run Retrieval Need Gate Challenge v2 Evaluation.")
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args()

    try:
        result = run_challenge_evaluation()
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

    report_path = save_report(result, args.output)
    print(
        json.dumps(
            {
                "status": result["acceptance"]["status"],
                "report_path": str(report_path),
                "challenge_frozen_commit": result["challenge_frozen_commit"],
                "protocol_frozen_commit": result["protocol_frozen_commit"],
                "gate_v2_commit": result["gate_v2_commit"],
                "gate": result["gate"],
                "end_to_end": {
                    "recall_at_1": result["end_to_end"]["recall_at_1"],
                    "recall_at_3": result["end_to_end"]["recall_at_3"],
                    "recall_at_5": result["end_to_end"]["recall_at_5"],
                    "precision_at_1": result["end_to_end"]["precision_at_1"],
                    "precision_at_3": result["end_to_end"]["precision_at_3"],
                    "precision_at_5": result["end_to_end"]["precision_at_5"],
                    "mrr": result["end_to_end"]["mrr"],
                    "no_hit_accuracy": result["end_to_end"]["no_hit_accuracy"],
                    "negative_no_hit_by_type": result["end_to_end"]["negative_no_hit_by_type"],
                    "source_category_match": result["end_to_end"]["source_category_match"],
                    "context_pollution_rate": result["end_to_end"]["context_pollution_rate"],
                    "fallback_count": result["end_to_end"]["fallback_count"],
                    "gate_failure_count": result["end_to_end"]["gate_failure_count"],
                    "retrieval_failure_count": result["end_to_end"]["retrieval_failure_count"],
                },
                "acceptance": result["acceptance"],
                "false_positive_count": len(result["false_positives"]),
                "false_negative_count": len(result["false_negatives"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
