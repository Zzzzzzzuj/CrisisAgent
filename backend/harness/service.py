from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.harness.spec import build_default_harness_spec, new_harness_id, snapshot_with_metadata, validate_harness_spec
from backend.harness.store import get_harness_repository


def list_harness_versions() -> list[dict[str, Any]]:
    return [build_default_harness_spec(), *get_harness_repository().list_specs()]


def get_effective_harness_spec(harness_id: str | None = None, version: str | None = None) -> dict[str, Any]:
    candidates = list_harness_versions()
    if harness_id or version:
        for spec in candidates:
            metadata = spec.get("metadata", {})
            if metadata.get("harness_id") == harness_id and (version is None or metadata.get("version") == version):
                if metadata.get("status") in {"active", "draft", "DRAFT", "EVALUATED", "APPROVED", "ACTIVE"}:
                    return deepcopy(spec)
        raise ValueError(f"HarnessSpec not found: {harness_id}@{version or '*'}")
    active = [item for item in candidates if item.get("metadata", {}).get("status") == "active"]
    return deepcopy(active[-1] if active else candidates[0])


def create_harness_version(spec: dict[str, Any], parent_version: str | None = None) -> dict[str, Any]:
    candidate = validate_harness_spec(spec)
    metadata = candidate.setdefault("metadata", {})
    metadata.setdefault("harness_id", new_harness_id())
    metadata.setdefault("version", "1.0.0")
    metadata.setdefault("status", "draft")
    metadata.setdefault("created_at", _now())
    metadata.setdefault("description", "Offline HarnessSpec candidate.")
    metadata["parent_version"] = parent_version
    return get_harness_repository().save(snapshot_with_metadata(candidate))


def set_harness_enabled(harness_id: str, version: str) -> dict[str, Any]:
    repository = get_harness_repository()
    specs = repository.list_specs()
    target = None
    for item in specs:
        metadata = item.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            target = item
        elif metadata.get("status") in {"active", "ACTIVE"}:
            # Keep the previous version approvable so an operator can roll back to it.
            metadata["status"] = "APPROVED"
    if target is None:
        raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")
    target["metadata"]["status"] = "active"
    repository.replace(specs)
    return deepcopy(target)


def rollback_harness_version(harness_id: str, version: str) -> dict[str, Any]:
    repository = get_harness_repository()
    specs = repository.list_specs()
    target = None
    for item in specs:
        metadata = item.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version and metadata.get("status") in {"ACTIVE", "active"}:
            return deepcopy(item)
        if metadata.get("status") in {"active", "ACTIVE"}:
            metadata["status"] = "ROLLED_BACK"
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            target = item
    if target is None:
        raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")
    if target.get("metadata", {}).get("status") not in {"APPROVED", "ACTIVE", "active"}:
        raise ValueError("Only APPROVED or ACTIVE HarnessSpec can be rolled back to.")
    target["metadata"]["status"] = "ACTIVE"
    repository.replace(specs)
    return deepcopy(target)


def copy_harness_version(source_id: str, source_version: str, new_version: str) -> dict[str, Any]:
    source = get_effective_harness_spec(source_id, source_version)
    copied = deepcopy(source)
    # Keep the P21 lowercase value for callers that already depend on it.
    copied["metadata"].update({"version": new_version, "status": "draft", "parent_version": source_version, "created_at": _now(), "change_summary": "Copied from parent version.", "changed_fields": []})
    return get_harness_repository().save(copied)


ALLOWED_CANDIDATE_FIELDS = {
    "skills_tools.execution_budget.max_steps",
    "skills_tools.execution_budget.max_retries",
    "skills_tools.execution_budget.max_runtime_ms",
    "skills_tools.execution_budget.max_same_call",
    "retrieval_policy.min_score",
    "retrieval_policy.min_rerank_score",
    "retrieval_policy.max_context_pollution_rate",
    "retrieval_policy.evidence_gate_human_review",
    "review_policy.triggers.evidence_low_confidence",
    "review_policy.triggers.evidence_conflict",
    "review_policy.triggers.tool_timeout",
    "review_policy.triggers.review_scope_mismatch",
}


def update_candidate_harness(harness_id: str, version: str, changes: dict[str, Any], change_summary: str) -> dict[str, Any]:
    if not isinstance(changes, dict) or not change_summary.strip():
        raise ValueError("Candidate changes and change_summary are required.")
    changed_fields = sorted(changes)
    invalid = [field for field in changed_fields if field not in ALLOWED_CANDIDATE_FIELDS]
    if invalid:
        raise ValueError("Candidate may only change tools_policy, retrieval_policy, and review_policy fields.")
    repository = get_harness_repository()
    specs = repository.list_specs()
    for spec in specs:
        metadata = spec.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            if str(metadata.get("status", "")).upper() not in {"DRAFT", "REJECTED"}:
                raise ValueError("Only DRAFT or REJECTED candidates can be edited.")
            updated = deepcopy(spec)
            for path, value in changes.items():
                _set_path(updated, path, value)
            validate_candidate_mutations(updated)
            updated["metadata"].update({"change_summary": change_summary, "changed_fields": changed_fields, "status": "draft"})
            validate_harness_spec(updated)
            specs[specs.index(spec)] = updated
            repository.replace(specs)
            return deepcopy(updated)
    raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")


def validate_candidate_mutations(spec: dict[str, Any]) -> None:
    retrieval = spec.get("retrieval_policy", {})
    for key in ("min_score", "min_rerank_score", "max_context_pollution_rate"):
        if key in retrieval and (not isinstance(retrieval[key], (int, float)) or isinstance(retrieval[key], bool) or retrieval[key] < 0):
            raise ValueError(f"{key} must be a non-negative number.")
    if "max_context_pollution_rate" in retrieval and retrieval["max_context_pollution_rate"] > 1:
        raise ValueError("max_context_pollution_rate must be at most 1.")
    budget = spec.get("skills_tools", {}).get("execution_budget", {})
    for key in ("max_steps", "max_runtime_ms", "max_same_call"):
        if key in budget and (not isinstance(budget[key], int) or isinstance(budget[key], bool) or budget[key] <= 0):
            raise ValueError(f"{key} must be a positive integer.")
    if "max_retries" in budget and (not isinstance(budget["max_retries"], int) or isinstance(budget["max_retries"], bool) or budget["max_retries"] < 0):
        raise ValueError("max_retries must be a non-negative integer.")


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = target
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = deepcopy(value)


def approve_harness_version(harness_id: str, version: str, comparison_id: str, reviewer: str, gate_result: dict[str, Any]) -> dict[str, Any]:
    repository = get_harness_repository()
    specs = repository.list_specs()
    for spec in specs:
        metadata = spec.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            if metadata.get("status") == "APPROVED":
                approval = metadata.get("approval", {})
                if approval.get("comparison_id") == comparison_id:
                    return deepcopy(spec)
                raise ValueError("HarnessSpec is already approved by another comparison.")
            if metadata.get("status") != "EVALUATED":
                raise ValueError("Only EVALUATED HarnessSpec can be approved.")
            metadata.update({"status": "APPROVED", "approval": {"comparison_id": comparison_id, "reviewer": reviewer, "approved_at": _now(), "reason": gate_result.get("reason", ""), "gate_result": deepcopy(gate_result)}})
            repository.replace(specs)
            return deepcopy(spec)
    raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")


def reject_harness_version(harness_id: str, version: str, reviewer: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("Rejection reason is required.")
    repository = get_harness_repository()
    specs = repository.list_specs()
    for spec in specs:
        metadata = spec.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            if str(metadata.get("status", "")).upper() not in {"DRAFT", "EVALUATED"}:
                raise ValueError("Only DRAFT or EVALUATED candidates can be rejected.")
            metadata.update({"status": "REJECTED", "rejection": {"reviewer": reviewer, "rejected_at": _now(), "reason": reason}})
            repository.replace(specs)
            return deepcopy(spec)
    raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")


def enable_approved_harness_version(harness_id: str, version: str) -> dict[str, Any]:
    spec = get_effective_harness_spec(harness_id, version)
    if spec.get("metadata", {}).get("status") in {"active", "ACTIVE"}:
        return spec
    if spec.get("metadata", {}).get("status") != "APPROVED":
        raise ValueError("Only APPROVED HarnessSpec can be enabled.")
    return set_harness_enabled(harness_id, version)


def mark_harness_evaluated(harness_id: str, version: str, comparison_id: str, gate_result: dict[str, Any]) -> dict[str, Any]:
    repository = get_harness_repository()
    specs = repository.list_specs()
    for spec in specs:
        metadata = spec.get("metadata", {})
        if metadata.get("harness_id") == harness_id and metadata.get("version") == version:
            if str(metadata.get("status", "")).upper() not in {"DRAFT", "REJECTED"}:
                raise ValueError("Only DRAFT or REJECTED candidates can be evaluated.")
            metadata.update({"status": "EVALUATED", "comparison_id": comparison_id, "gate_result": deepcopy(gate_result)})
            repository.replace(specs)
            return deepcopy(spec)
    raise KeyError(f"HarnessSpec not found: {harness_id}@{version}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
