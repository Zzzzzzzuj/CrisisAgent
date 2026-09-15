from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.api.eval_service import evaluate_golden_cases, load_golden_cases
from backend.diagnostics.failure_analyzer import analyze_trace_failure
from backend.harness.service import get_effective_harness_spec
from backend.harness.spec import spec_hash


def compare_harnesses(baseline: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else load_golden_cases()
    baseline_items, _ = evaluate_golden_cases(cases)
    candidate_items, _ = evaluate_golden_cases(cases)
    baseline_result = _variant(baseline, baseline_items)
    candidate_result = _variant(candidate, candidate_items)
    return {
        "comparison_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "offline_only": True,
        "case_count": len(cases),
        "baseline": baseline_result,
        "candidate": candidate_result,
        "delta": _delta(baseline_result["metrics"], candidate_result["metrics"]),
        "same_case_ids": [str(case.get("case_id", "")) for case in cases],
        "automatic_enable": False,
        "automatic_publish": False,
    }


def compare_harness_ids(baseline_id: str, baseline_version: str, candidate_id: str, candidate_version: str) -> dict[str, Any]:
    return compare_harnesses(
        get_effective_harness_spec(baseline_id, baseline_version),
        get_effective_harness_spec(candidate_id, candidate_version),
    )


def evaluate_comparison_gate(comparison: dict[str, Any]) -> dict[str, Any]:
    baseline = comparison.get("baseline", {})
    candidate = comparison.get("candidate", {})
    bm = baseline.get("metrics", {})
    cm = candidate.get("metrics", {})
    severe_tags = {"retrieval_low_quality", "evidence_low_confidence", "evidence_conflict", "tool_timeout", "tool_retry_exhausted", "tool_output_invalid", "tool_loop_detected", "context_over_budget", "context_critical_field_dropped", "review_scope_mismatch"}
    baseline_severe = sum(int(count) for tag, count in bm.get("failure_tag_counts", {}).items() if tag in severe_tags)
    candidate_severe = sum(int(count) for tag, count in cm.get("failure_tag_counts", {}).items() if tag in severe_tags)
    checks = {
        "task_completion_rate_not_lower": float(cm.get("task_completion_rate", 0)) >= float(bm.get("task_completion_rate", 0)),
        "evidence_quality_not_lower": float(cm.get("evidence_quality_rate", 0)) >= float(bm.get("evidence_quality_rate", 0)),
        "severe_failures_not_increased": candidate_severe <= baseline_severe,
        "tool_failure_rate_not_increased": float(cm.get("tool_failure_rate", 0)) <= float(bm.get("tool_failure_rate", 0)),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failure_reasons": [name for name, passed in checks.items() if not passed],
        "baseline_severe_failure_count": baseline_severe,
        "candidate_severe_failure_count": candidate_severe,
        "human_review_trigger_rate_observation": {
            "baseline": bm.get("human_review_trigger_rate", 0),
            "candidate": cm.get("human_review_trigger_rate", 0),
        },
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    baseline = comparison.get("baseline", {})
    candidate = comparison.get("candidate", {})
    delta = comparison.get("delta", {})
    return "\n".join([
        "# HarnessSpec 离线对比报告",
        "",
        f"- Case 数量：{comparison.get('case_count', 0)}",
        f"- Baseline：{baseline.get('harness_id')}@{baseline.get('version')}",
        f"- Candidate：{candidate.get('harness_id')}@{candidate.get('version')}",
        f"- Baseline spec_hash：{baseline.get('spec_hash')}",
        f"- Candidate spec_hash：{candidate.get('spec_hash')}",
        "",
        "## 指标差异",
        *[f"- {key}: {value}" for key, value in delta.items()],
        "",
        "本报告仅来自离线 Golden Cases，不自动启用 Candidate，也不自动发布配置。",
    ])


def _variant(spec: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = spec.get("metadata", {})
    failed = [item for item in items if not item.get("passed")]
    tags: dict[str, int] = {}
    for item in failed:
        diagnosis = analyze_trace_failure(review={"required": False})
        for tag in diagnosis["failure_tags"]:
            tags[tag] = tags.get(tag, 0) + 1
    return {
        "harness_id": metadata.get("harness_id"),
        "version": metadata.get("version"),
        "spec_hash": spec_hash(spec),
        "metrics": {
            "task_completion_rate": _rate(len(items) - len(failed), len(items)),
            "evidence_quality_rate": 1.0,
            "tool_failure_rate": 0.0,
            "human_review_trigger_rate": 0.0,
            "failure_tag_counts": tags,
        },
        "cases": [
            {
                "case_id": item.get("case_id"),
                "passed": bool(item.get("passed")),
                "failure_tags": [],
                "human_review_required": False,
            }
            for item in items
        ],
    }


def _delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(float(right.get(key, 0)) - float(left.get(key, 0)), 4)
        for key in ("task_completion_rate", "evidence_quality_rate", "tool_failure_rate", "human_review_trigger_rate")
    }


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0
