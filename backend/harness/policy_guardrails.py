from __future__ import annotations

from copy import deepcopy
from typing import Any


CRITICAL_REVIEW_FIELDS = {
    "review_policy.triggers.evidence_conflict",
    "review_policy.triggers.review_scope_mismatch",
}


def _get(spec: dict[str, Any], path: str, default=None):
    node: Any = spec
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part, default)
    return deepcopy(node)


def analyze_policy_diff(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    paths = [
        "retrieval_policy.min_score", "retrieval_policy.min_rerank_score",
        "retrieval_policy.max_context_pollution_rate", "retrieval_policy.evidence_gate_human_review",
        "review_policy.triggers.evidence_low_confidence", "review_policy.triggers.evidence_conflict",
        "review_policy.triggers.tool_timeout", "review_policy.triggers.review_scope_mismatch",
        "skills_tools.timeout_ms", "skills_tools.max_retries",
        "skills_tools.execution_budget.max_steps", "skills_tools.execution_budget.max_retries",
        "skills_tools.execution_budget.max_runtime_ms", "skills_tools.execution_budget.max_same_call",
    ]
    changes = []
    for path in paths:
        old, new = _get(baseline, path), _get(candidate, path)
        defaults = {"skills_tools.timeout_ms": 3000, "skills_tools.max_retries": 0}
        if old is None and path in defaults:
            old = defaults[path]
        if new is None and path in defaults:
            new = defaults[path]
        if old == new:
            continue
        category, reason = _classify(path, old, new)
        changes.append({"field": path, "baseline": old, "candidate": new, "category": category, "reason": reason, "critical": path in CRITICAL_REVIEW_FIELDS})
    weakening = [item for item in changes if item["category"] == "safety_weakening"]
    blocked = [item["field"] for item in weakening if item["field"] in CRITICAL_REVIEW_FIELDS]
    return {
        "changed": bool(changes),
        "changes": changes,
        "categories": sorted({item["category"] for item in changes}),
        "safety_weakening": bool(weakening),
        "safety_weakening_fields": [item["field"] for item in weakening],
        "blocked_fields": blocked,
        "requires_explicit_approval_reason": bool(weakening),
        "affected_harness_areas": sorted({item["field"].split(".", 1)[0] for item in changes}),
    }


def validate_policy_diff(diff: dict[str, Any], *, allow_critical_weakening: bool = False) -> None:
    if diff.get("blocked_fields") and not allow_critical_weakening:
        raise ValueError("Candidate cannot disable critical Human Review triggers: " + ", ".join(diff["blocked_fields"]))


def evaluate_policy_safety_gate(comparison: dict[str, Any]) -> dict[str, Any]:
    diff = comparison.get("policy_diff") or {}
    baseline = comparison.get("baseline", {}).get("cases", [])
    candidate = comparison.get("candidate", {}).get("cases", [])
    baseline_review = sum(bool(item.get("human_review_required")) for item in baseline)
    candidate_review = sum(bool(item.get("human_review_required")) for item in candidate)
    coverage_ok = candidate_review >= baseline_review
    mode = comparison.get("mode", "golden")
    replay_coverage_available = mode == "main_workflow_replay" and bool(baseline) and all("human_review_required" in item for item in baseline + candidate)
    passed = not diff.get("blocked_fields") and (not diff.get("safety_weakening") or (replay_coverage_available and coverage_ok))
    return {
        "passed": passed,
        "safety_weakening": bool(diff.get("safety_weakening")),
        "blocked_fields": list(diff.get("blocked_fields", [])),
        "critical_review_coverage_not_lower": coverage_ok,
        "baseline_required_review_cases": baseline_review,
        "candidate_required_review_cases": candidate_review,
        "replay_coverage_available": replay_coverage_available,
        "reason": "" if passed else "Candidate weakens safety policy or reduces required review coverage.",
    }


def _classify(path: str, old: Any, new: Any) -> tuple[str, str]:
    if path.endswith("evidence_gate_human_review"):
        return ("safety_weakening", "Evidence Gate no longer sends low-confidence evidence to review.") if new is False else ("safe", "Evidence Gate review remains enabled or is tightened.")
    if path.startswith("review_policy.triggers."):
        if new is False:
            return "safety_weakening", "A Human Review trigger is disabled."
        return "safe", "A Human Review trigger is enabled."
    if path.endswith("max_context_pollution_rate"):
        return ("safety_weakening", "Higher pollution tolerance allows noisier evidence.") if float(new) > float(old) else ("safe", "Lower pollution tolerance is stricter.")
    if path.endswith("min_score") or path.endswith("min_rerank_score"):
        return ("safety_weakening", "Lower evidence threshold accepts weaker evidence.") if float(new) < float(old) else ("safe", "Higher evidence threshold is stricter.")
    if path.endswith("timeout_ms"):
        return ("safe", "More timeout budget reduces premature tool failure.") if int(new) >= int(old) else ("review_required", "Less timeout budget may increase tool failures.")
    if path.endswith("max_retries"):
        return ("safe", "More retries can recover transient tool failures.") if int(new) >= int(old) else ("review_required", "Fewer retries can reduce recovery.")
    if ".execution_budget." in path:
        return ("review_required", "A larger execution budget permits more work and needs review.") if float(new) > float(old) else ("safe", "A smaller execution budget bounds execution more tightly.")
    return "review_required", "This policy change needs human review."
