from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.harness.service import ALLOWED_CANDIDATE_FIELDS
from backend.harness.spec import spec_hash
from backend.harness.policy_guardrails import analyze_policy_diff


TAG_TO_FIELDS = {
    "tool_timeout": ["skills_tools.execution_budget.max_runtime_ms"],
    "tool_retry_exhausted": ["skills_tools.execution_budget.max_retries"],
    "tool_loop_detected": ["skills_tools.execution_budget.max_same_call"],
    "context_over_budget": [],
    "context_critical_field_dropped": [],
    "evidence_low_confidence": ["retrieval_policy.min_score", "retrieval_policy.min_rerank_score", "retrieval_policy.evidence_gate_human_review"],
    "evidence_conflict": ["review_policy.triggers.evidence_conflict"],
    "review_scope_mismatch": ["review_policy.triggers.review_scope_mismatch"],
}


def build_proposal(diagnosis: dict[str, Any], baseline: dict[str, Any], *, source_run_id: str | None = None, comparison_id: str | None = None, replay_case_id: str | None = None) -> dict[str, Any]:
    tags = list(dict.fromkeys(str(tag) for tag in diagnosis.get("failure_tags", [])))
    fields = sorted({field for tag in tags for field in TAG_TO_FIELDS.get(tag, []) if field in ALLOWED_CANDIDATE_FIELDS})
    allowed_patch = _safe_patch(baseline, fields)
    context_tags = [tag for tag in tags if tag in {"context_over_budget", "context_critical_field_dropped"}]
    reasons = [f"{tag} maps to {', '.join(TAG_TO_FIELDS.get(tag, [])) or 'context_policy review only'}" for tag in tags]
    metadata = baseline.get("metadata", {})
    proposed = deepcopy(baseline)
    for field, value in allowed_patch.items():
        _set_path(proposed, field, value)
    policy_diff = analyze_policy_diff(baseline, proposed)
    return {
        "proposal_id": f"proposal-{uuid4()}",
        "source_run_id": source_run_id,
        "comparison_id": comparison_id,
        "replay_case_id": replay_case_id,
        "baseline_harness_id": metadata.get("harness_id"),
        "baseline_version": metadata.get("version"),
        "spec_hash": spec_hash(baseline),
        "failure_tags": tags,
        "diagnosis_summary": diagnosis.get("diagnosis_summary", ""),
        "evidence_refs": diagnosis.get("evidence_refs", []),
        "recommended_harness_areas": diagnosis.get("recommended_harness_areas", []),
        "allowed_patch": allowed_patch,
        "rationale": "; ".join(reasons) or "No deterministic failure tag was provided.",
        "risk_notes": ["Advisory only; no HarnessSpec changes occur until manual acceptance."] + (["Context compression requires manual context_policy review; no automatic patch is generated."] if context_tags else []) + (["Policy diff contains a safety weakening and requires explicit human review."] if policy_diff.get("safety_weakening") else []),
        "policy_diff": policy_diff,
        "expected_validation": {"replay_case_ids": [replay_case_id] if replay_case_id else [], "golden_cases": True},
        "status": "DRAFT",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": None,
        "review_reason": "",
    }


def validate_allowed_patch(patch: dict[str, Any]) -> None:
    invalid = [field for field in patch if field not in ALLOWED_CANDIDATE_FIELDS]
    if invalid:
        raise ValueError("Proposal patch contains fields outside the Harness candidate allowlist.")
    if any(field.startswith("context_policy") for field in patch):
        raise ValueError("Context policy proposals are advisory only in this phase.")
    if any(field.startswith("review_policy") and patch[field] is False for field in patch):
        raise ValueError("Proposal cannot automatically lower Human Review requirements.")


def _safe_patch(baseline: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in fields:
        current = _get_path(baseline, field)
        if field.endswith("max_runtime_ms"):
            patch[field] = min(int(current or 5000) * 2, 10000)
        elif field.endswith("max_retries"):
            patch[field] = min(int(current or 0) + 1, 3)
        elif field.endswith("max_same_call"):
            patch[field] = max(1, int(current or 1))
        elif field.endswith("evidence_gate_human_review") or field.endswith("evidence_conflict"):
            patch[field] = True
        elif field.endswith("min_score") or field.endswith("min_rerank_score"):
            patch[field] = float(current if current is not None else 0.1)
    validate_allowed_patch(patch)
    return patch


def _get_path(source: dict[str, Any], path: str) -> Any:
    node: Any = source
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return deepcopy(node)


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    node = target
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = deepcopy(value)
