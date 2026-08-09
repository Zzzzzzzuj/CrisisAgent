import argparse
import json
import sys
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.retrieval_need_gate import evaluate_retrieval_need


RAG_CASES_PATH = PROJECT_ROOT / "evaluation" / "rag_cases_v2.json"
NEGATIVE_CALIBRATION_PATH = PROJECT_ROOT / "evaluation" / "rag_negative_calibration_v2.json"
CHALLENGE_V1_PATH = PROJECT_ROOT / "evaluation" / "rag_gate_challenge_v1.json"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_rag_gate_v2_development.md"

GATE_V1_CHALLENGE_FN_IDS = {
    "gate_challenge_food_safety_001",
    "gate_challenge_food_safety_002",
    "gate_challenge_food_safety_003",
    "gate_challenge_food_safety_004",
    "gate_challenge_data_privacy_001",
    "gate_challenge_data_privacy_002",
    "gate_challenge_data_privacy_004",
    "gate_challenge_service_outage_001",
    "gate_challenge_service_outage_002",
    "gate_challenge_service_outage_004",
    "gate_challenge_product_quality_001",
    "gate_challenge_product_quality_002",
    "gate_challenge_product_quality_003",
    "gate_challenge_executive_misconduct_002",
    "gate_challenge_executive_misconduct_003",
    "gate_challenge_executive_misconduct_004",
}


def run_gate_v2_development_evaluation() -> dict:
    development_positive = _load_development_positive_cases()
    calibration_negative = _load_negative_calibration_cases()
    challenge_v1 = _load_json(CHALLENGE_V1_PATH)

    development_results = evaluate_gate_cases(
        development_positive,
        text_field="query",
        expected_need=True,
    )
    calibration_results = evaluate_gate_cases(
        calibration_negative,
        text_field="query",
        expected_need=False,
    )
    challenge_results = evaluate_gate_cases(
        challenge_v1,
        text_field="event",
        expected_need=lambda case: case["label"] == "need_rag",
    )

    challenge_summary = summarize_gate_results(challenge_results)
    original_fn_results = [
        result for result in challenge_results
        if result["case_id"] in GATE_V1_CHALLENGE_FN_IDS
    ]
    original_tn_results = [
        result for result in challenge_results
        if result["expected_need"] is False
    ]
    recovered_false_negatives = [
        result for result in original_fn_results
        if result["need_rag"] is True
    ]
    remaining_false_negatives = [
        result for result in original_fn_results
        if result["need_rag"] is False
    ]
    new_false_positives = [
        result for result in original_tn_results
        if result["need_rag"] is True
    ]

    return {
        "experiment": "Retrieval Need Gate v2 Development",
        "production_integration_changed": False,
        "old_final_run": False,
        "challenge_v1_usage": "post-hoc regression only",
        "gate_v1_challenge_first_run": {
            "TP": 4,
            "TN": 20,
            "FP": 0,
            "FN": 16,
            "tpr": 0.20,
            "tnr": 1.00,
            "status": "FAIL",
        },
        "development": summarize_gate_results(development_results),
        "calibration": summarize_gate_results(calibration_results),
        "challenge_v1_post_hoc": challenge_summary,
        "challenge_v1_category_tpr": summarize_positive_category_tpr(challenge_results),
        "original_fn_v2_results": original_fn_results,
        "new_false_positives": new_false_positives,
        "recovered_false_negatives": len(recovered_false_negatives),
        "remaining_false_negatives": len(remaining_false_negatives),
        "new_false_positive_count": len(new_false_positives),
        "architecture_changes": [
            "ambiguous enterprise risk defaults to need_rag=true",
            "only high-confidence negative intent rejects retrieval",
            "information_lookup requires combined lookup evidence instead of single response words",
            "decision_score is retained for trace/debug but no longer acts as the sole decision threshold",
        ],
        "signal_expansions": [
            "added harm_or_anomaly signal group",
            "added enterprise_context signal group",
            "expanded policy/business/customer-service phrase coverage for high-confidence negative intent",
        ],
    }


def evaluate_gate_cases(
    cases: list[dict],
    text_field: str,
    expected_need: bool | Callable[[dict], bool],
) -> list[dict]:
    results = []
    for case in cases:
        expected = expected_need(case) if callable(expected_need) else expected_need
        text = case[text_field]
        gate = evaluate_retrieval_need(text)
        results.append(
            {
                "case_id": case["id"],
                "category": case.get("category", case.get("type", "unknown")),
                "type": case.get("type"),
                "text": text,
                "expected_need": bool(expected),
                "need_rag": gate["need_rag"],
                "intent": gate["intent"],
                "decision_score": gate["decision_score"],
                "matched_signals": gate["matched_signals"],
                "negative_signals": gate["negative_signals"],
                "reason": gate["reason"],
                "gate_label": _gate_label(bool(expected), gate["need_rag"]),
            }
        )
    return results


def summarize_gate_results(results: list[dict]) -> dict:
    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for result in results:
        counts[result["gate_label"]] += 1
    return {
        **counts,
        "tpr": _safe_rate(counts["TP"], counts["TP"] + counts["FN"]),
        "tnr": _safe_rate(counts["TN"], counts["TN"] + counts["FP"]),
        "fpr": _safe_rate(counts["FP"], counts["FP"] + counts["TN"]),
        "fnr": _safe_rate(counts["FN"], counts["FN"] + counts["TP"]),
        "hard_negative_reject_rate": _reject_rate(results, "hard_negative"),
        "false_positives": [result for result in results if result["gate_label"] == "FP"],
        "false_negatives": [result for result in results if result["gate_label"] == "FN"],
    }


def summarize_positive_category_tpr(results: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for result in results:
        if result["expected_need"]:
            grouped.setdefault(result["category"], []).append(result)
    return {
        category: {
            "TP": sum(1 for item in items if item["gate_label"] == "TP"),
            "FN": sum(1 for item in items if item["gate_label"] == "FN"),
            "tpr": _safe_rate(
                sum(1 for item in items if item["gate_label"] == "TP"),
                len(items),
            ),
        }
        for category, items in sorted(grouped.items())
    }


def save_report(result: dict, report_path: str | Path = REPORT_PATH) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(result), encoding="utf-8")
    return path


def build_markdown_report(result: dict) -> str:
    lines = [
        "# CrisisAgent Retrieval Need Gate v2 Development Report",
        "",
        "## Scope",
        "",
        "- Gate version: `v2 Conservative Reject Gate`",
        "- Production Legal Agent path changed: `False`",
        "- Structured state used: `False`",
        "- BGE / Retriever / KB / Prompt changed: `False`",
        "- Challenge v1 usage: `post-hoc regression only`",
        "- This report must not be described as a new independent Challenge result.",
        "",
        "## Historical Baseline",
        "",
        "- Gate v1 Challenge v1 FIRST RUN: `TP=4, TN=20, FP=0, FN=16`",
        "- Gate v1 Challenge v1 TPR: `0.20`",
        "- Gate v1 Challenge v1 TNR: `1.00`",
        "- Gate v1 Challenge v1 Status: `FAIL`",
        "",
        "## Development Positive",
        "",
    ]
    lines.extend(_summary_lines(result["development"]))
    lines.extend(["", "## Negative Calibration", ""])
    lines.extend(_summary_lines(result["calibration"]))
    lines.extend(["", "## Challenge v1 Post-Hoc Regression", ""])
    lines.extend(_summary_lines(result["challenge_v1_post_hoc"]))
    lines.extend(["", "## Challenge v1 Positive Category TPR", ""])
    for category, metrics in result["challenge_v1_category_tpr"].items():
        lines.append(f"- `{category}`: TP={metrics['TP']}, FN={metrics['FN']}, TPR={metrics['tpr']}")
    lines.extend(
        [
            "",
            "## Gate v1 False Negative Recovery",
            "",
            f"- recovered_false_negatives: `{result['recovered_false_negatives']}`",
            f"- remaining_false_negatives: `{result['remaining_false_negatives']}`",
            f"- new_false_positives: `{result['new_false_positive_count']}`",
            "",
            "### Original 16 FN Under Gate v2",
            "",
        ]
    )
    lines.extend(_case_lines(result["original_fn_v2_results"]))
    lines.extend(["", "### New FP Under Gate v2", ""])
    lines.extend(_case_lines(result["new_false_positives"]))
    lines.extend(["", "## Architecture Changes", ""])
    lines.extend(f"- {item}" for item in result["architecture_changes"])
    lines.extend(["", "## Signal / Keyword Expansions", ""])
    lines.extend(f"- {item}" for item in result["signal_expansions"])
    lines.extend(
        [
            "",
            "## Risk",
            "",
            "- Gate v2 intentionally shifts toward recall-first behavior, so false positives can increase.",
            "- Challenge v1 is no longer untouched and can only guide diagnosis; Gate v2 needs a new Challenge v2 for final validation.",
        ]
    )
    return "\n".join(lines)


def _summary_lines(summary: dict) -> list[str]:
    return [
        f"- TP: `{summary['TP']}`",
        f"- TN: `{summary['TN']}`",
        f"- FP: `{summary['FP']}`",
        f"- FN: `{summary['FN']}`",
        f"- TPR: `{summary['tpr']}`",
        f"- TNR: `{summary['tnr']}`",
        f"- FPR: `{summary['fpr']}`",
        f"- FNR: `{summary['fnr']}`",
        f"- hard_negative_reject_rate: `{summary['hard_negative_reject_rate']}`",
    ]


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
                f"- expected_need: `{case['expected_need']}`",
                f"- need_rag: `{case['need_rag']}`",
                f"- intent: `{case['intent']}`",
                f"- decision_score: `{case['decision_score']}`",
                f"- matched_signals: `{case['matched_signals']}`",
                f"- negative_signals: `{case['negative_signals']}`",
                f"- reason: {case['reason']}",
                f"- text: {case['text']}",
                "",
            ]
        )
    return lines


def _load_development_positive_cases() -> list[dict]:
    return [
        case for case in _load_json(RAG_CASES_PATH)
        if case.get("split") == "development" and case.get("expected_hit") is True
    ]


def _load_negative_calibration_cases() -> list[dict]:
    return _load_json(NEGATIVE_CALIBRATION_PATH)


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_label(expected_need: bool, need_rag: bool) -> str:
    if expected_need and need_rag:
        return "TP"
    if expected_need and not need_rag:
        return "FN"
    if not expected_need and need_rag:
        return "FP"
    return "TN"


def _reject_rate(results: list[dict], result_type: str) -> float:
    items = [item for item in results if item.get("type") == result_type]
    if not items:
        return 0.0
    return _safe_rate(sum(1 for item in items if item["gate_label"] == "TN"), len(items))


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gate v2 development evaluation.")
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args()
    result = run_gate_v2_development_evaluation()
    report_path = save_report(result, args.output)
    print(
        json.dumps(
            {
                "status": "OK",
                "report_path": str(report_path),
                "development": result["development"],
                "calibration": result["calibration"],
                "challenge_v1_post_hoc": result["challenge_v1_post_hoc"],
                "recovered_false_negatives": result["recovered_false_negatives"],
                "remaining_false_negatives": result["remaining_false_negatives"],
                "new_false_positives": result["new_false_positive_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
