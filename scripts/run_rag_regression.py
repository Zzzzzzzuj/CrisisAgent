import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_rag_retrieval import DEFAULT_CASES_PATH, evaluate_cases, load_cases


DEFAULT_BASELINE_PATH = PROJECT_ROOT / "reports" / "rag_baseline.json"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "reports" / "rag_regression_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "reports" / "rag_regression_report.md"

DEFAULT_THRESHOLDS = {
    "top3_source_hit_rate_drop": 0.1,
    "fallback_rate_increase": 0.1,
    "context_pollution_rate_increase": 0.15,
}


def load_baseline(path: str | Path = DEFAULT_BASELINE_PATH) -> dict[str, Any] | None:
    baseline_path = Path(path)
    if not baseline_path.exists():
        return None
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def run_regression(
    cases: list[dict] | None = None,
    baseline: dict[str, Any] | None = None,
    retriever: Any | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    active_cases = cases if cases is not None else load_cases(DEFAULT_CASES_PATH)
    current_result = evaluate_cases(active_cases, retriever=retriever)
    active_thresholds = thresholds or DEFAULT_THRESHOLDS
    comparison = compare_to_baseline(current_result["summary"], baseline, active_thresholds)
    failed_cases = _failed_cases(current_result["cases"])
    return {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_cases": current_result["summary"]["total_cases"],
            "baseline_available": baseline is not None,
            "regression_passed": comparison["passed"],
            "checks": comparison["checks"],
            "thresholds": active_thresholds,
            "failed_case_count": len(failed_cases),
        },
        "current_metrics": current_result["summary"],
        "baseline_metrics": baseline,
        "failed_cases": failed_cases,
        "empty_knowledge_base_hint": current_result.get("empty_knowledge_base_hint", ""),
    }


def compare_to_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    if baseline is None:
        return {
            "passed": True,
            "checks": [
                {
                    "metric": "baseline",
                    "status": "skipped",
                    "reason": "baseline_not_found",
                }
            ],
        }

    active_thresholds = thresholds or DEFAULT_THRESHOLDS
    checks = [
        _min_allowed_check(
            metric="top3_source_hit_rate",
            current=current.get("top3_source_hit_rate"),
            baseline=baseline.get("top3_source_hit_rate"),
            allowed_drop=active_thresholds["top3_source_hit_rate_drop"],
        ),
        _max_allowed_check(
            metric="fallback_rate",
            current=current.get("fallback_rate"),
            baseline=baseline.get("fallback_rate"),
            allowed_increase=active_thresholds["fallback_rate_increase"],
        ),
    ]

    if (
        current.get("context_pollution_rate") is not None
        and baseline.get("context_pollution_rate") is not None
    ):
        checks.append(
            _max_allowed_check(
                metric="context_pollution_rate",
                current=current.get("context_pollution_rate"),
                baseline=baseline.get("context_pollution_rate"),
                allowed_increase=active_thresholds["context_pollution_rate_increase"],
            )
        )
    else:
        checks.append(
            {
                "metric": "context_pollution_rate",
                "status": "skipped",
                "reason": "metric_not_available",
                "current": current.get("context_pollution_rate"),
                "baseline": baseline.get("context_pollution_rate"),
            }
        )

    return {
        "passed": all(check["status"] != "failed" for check in checks),
        "checks": checks,
    }


def write_reports(
    result: dict[str, Any],
    json_path: str | Path = DEFAULT_REPORT_JSON,
    markdown_path: str | Path = DEFAULT_REPORT_MD,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_target.write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# RAG Regression Report",
        "",
        "This report compares the current Legal RAG retrieval metrics against the fixed project baseline.",
        "It is an offline regression check and does not call a real LLM.",
        "",
        "## Summary",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- total_cases: {summary['total_cases']}",
        f"- baseline_available: {summary['baseline_available']}",
        f"- regression_passed: {summary['regression_passed']}",
        f"- failed_case_count: {summary['failed_case_count']}",
        "",
        "## Current Metrics",
        "",
    ]
    for key, value in result["current_metrics"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Baseline Metrics", ""])
    if result["baseline_metrics"] is None:
        lines.append("- baseline: not found")
    else:
        for key, value in result["baseline_metrics"].items():
            lines.append(f"- {key}: {value}")

    lines.extend(["", "## Regression Checks", ""])
    for check in summary["checks"]:
        lines.append(
            f"- {check['metric']}: {check['status']} "
            f"(current={check.get('current')}, baseline={check.get('baseline')}, "
            f"limit={check.get('limit')}, reason={check.get('reason', '')})"
        )

    lines.extend(["", "## Failed Cases", ""])
    if not result["failed_cases"]:
        lines.append("- none")
    for case in result["failed_cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- expected_source_category: {case['expected_source_category']}",
                f"- actual_source_categories: {case['actual_source_categories']}",
                f"- failure_reason: {case['failure_reason']}",
                f"- possible_causes: {case['possible_causes']}",
                "",
            ]
        )

    if result.get("empty_knowledge_base_hint"):
        lines.extend(["## Empty Knowledge Base Hint", "", result["empty_knowledge_base_hint"], ""])

    return "\n".join(lines)


def main() -> int:
    baseline = load_baseline()
    result = run_regression(baseline=baseline)
    write_reports(result)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"JSON report: {DEFAULT_REPORT_JSON}")
    print(f"Markdown report: {DEFAULT_REPORT_MD}")
    return 0 if result["summary"]["regression_passed"] else 1


def _min_allowed_check(
    metric: str,
    current: float | None,
    baseline: float | None,
    allowed_drop: float,
) -> dict[str, Any]:
    if current is None or baseline is None:
        return {
            "metric": metric,
            "status": "skipped",
            "reason": "metric_not_available",
            "current": current,
            "baseline": baseline,
        }
    limit = round(baseline - allowed_drop, 4)
    return {
        "metric": metric,
        "status": "passed" if current >= limit else "failed",
        "reason": "below_allowed_floor" if current < limit else "",
        "current": current,
        "baseline": baseline,
        "limit": limit,
    }


def _max_allowed_check(
    metric: str,
    current: float | None,
    baseline: float | None,
    allowed_increase: float,
) -> dict[str, Any]:
    if current is None or baseline is None:
        return {
            "metric": metric,
            "status": "skipped",
            "reason": "metric_not_available",
            "current": current,
            "baseline": baseline,
        }
    limit = round(baseline + allowed_increase, 4)
    return {
        "metric": metric,
        "status": "passed" if current <= limit else "failed",
        "reason": "above_allowed_ceiling" if current > limit else "",
        "current": current,
        "baseline": baseline,
        "limit": limit,
    }


def _failed_cases(cases: list[dict]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for case in cases:
        if case["top3_source_hit"] and case["keyword_hit"]:
            continue
        failed.append(
            {
                "case_id": case["case_id"],
                "expected_source_category": case["expected_source_category"],
                "actual_source_categories": case["actual_source_categories"],
                "failure_reason": case["failure_reason"] or "unknown",
                "possible_causes": _possible_causes(case),
            }
        )
    return failed


def _possible_causes(case: dict[str, Any]) -> list[str]:
    reason = case.get("failure_reason")
    if reason == "no_retrieval_result":
        return ["knowledge_gap", "query_rewrite_issue", "low_score"]
    if reason == "expected_source_category_not_in_top3":
        return ["source_category_mismatch", "rerank_issue", "knowledge_gap"]
    if reason == "expected_keywords_missing":
        return ["chunk_issue", "knowledge_gap"]
    return ["knowledge_gap", "query_rewrite_issue", "chunk_issue", "rerank_issue"]


if __name__ == "__main__":
    raise SystemExit(main())
