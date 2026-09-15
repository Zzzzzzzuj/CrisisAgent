from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

def build_default_harness_spec() -> dict[str, Any]:
    """Return a JSON-safe snapshot of the rules already used by the runtime."""
    from backend.core.plan_validator import AGENT_DEPENDENCIES, AGENT_ORDER
    from backend.skills.builtins import create_default_registry

    tools = []
    for definition in create_default_registry().list_skills():
        tools.append({key: value for key, value in definition.items() if key != "handler"})
    now = datetime.now(timezone.utc).isoformat()
    return {
        "metadata": {
            "harness_id": "crisisagent-default",
            "version": "1.0.0",
            "status": "active",
            "created_at": now,
            "description": "Default CrisisAgent runtime rules, derived from existing behavior.",
            "parent_version": None,
        },
        "workflow": {
            "agent_order": list(AGENT_ORDER),
            "enabled_roles": list(AGENT_ORDER),
            "dependencies": deepcopy(AGENT_DEPENDENCIES),
        },
        "prompts": {
            "mode": "existing_runtime_prompts",
            "versions": {agent: "default" for agent in AGENT_ORDER},
        },
        "skills_tools": {
            "definitions": tools,
            "allowed_tools": [item["name"] for item in tools],
            "execution_budget": {
                "max_steps": 6,
                "max_retries": 1,
                "max_runtime_ms": 5000,
                "max_same_call": 1,
            },
        },
        "context_policy": {
            "context_pack": "existing_context_pack_policy",
            "case_memory": "existing_case_memory_policy",
            "compression": "risk_aware_waterline",
            "role_retention": "target_agent_specific",
        },
        "retrieval_policy": {
            "need_gate": "existing_retrieval_need_gate",
            "retrieval": "hybrid_keyword_vector",
            "rerank": "existing_reranker",
            "evidence_gate": "existing_evidence_quality_gate",
            "min_score": 0.1,
            "min_rerank_score": 0.1,
            "max_context_pollution_rate": 0.5,
            "evidence_gate_human_review": True,
        },
        "review_policy": {
            "policy": "existing_human_review_policy",
            "approval_scope": "reviewed_trace_scope",
            "auto_publish": False,
            "triggers": {
                "evidence_low_confidence": True,
                "evidence_conflict": True,
                "tool_timeout": True,
            },
        },
    }


def validate_harness_spec(spec: dict[str, Any]) -> dict[str, Any]:
    from backend.core.plan_validator import AGENT_DEPENDENCIES, AGENT_ORDER

    if not isinstance(spec, dict):
        raise ValueError("HarnessSpec must be a JSON object.")
    metadata = spec.get("metadata")
    workflow = spec.get("workflow")
    if not isinstance(metadata, dict) or not metadata.get("harness_id") or not metadata.get("version"):
        raise ValueError("HarnessSpec metadata must include harness_id and version.")
    if not isinstance(workflow, dict) or workflow.get("agent_order") != list(AGENT_ORDER):
        raise ValueError("HarnessSpec must preserve the default Agent order.")
    if set(workflow.get("dependencies", {})) != set(AGENT_DEPENDENCIES):
        raise ValueError("HarnessSpec dependencies must cover the registered Agents.")
    if metadata.get("status") not in {"draft", "active", "disabled", "archived", "DRAFT", "EVALUATED", "APPROVED", "REJECTED", "ACTIVE", "ROLLED_BACK"}:
        raise ValueError("Unsupported HarnessSpec status.")
    return deepcopy(spec)


def snapshot_with_metadata(spec: dict[str, Any], *, status: str | None = None) -> dict[str, Any]:
    snapshot = validate_harness_spec(spec)
    if status is not None:
        snapshot["metadata"]["status"] = status
    return snapshot


def spec_hash(spec: dict[str, Any]) -> str:
    normalized = validate_harness_spec(spec)
    metadata = normalized.get("metadata", {})
    for volatile in ("created_at", "status", "approval", "rejection", "comparison_id", "gate_result", "change_summary", "changed_fields"):
        metadata.pop(volatile, None)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def harness_trace_reference(spec: dict[str, Any]) -> dict[str, str]:
    metadata = spec.get("metadata", {})
    return {
        "harness_id": str(metadata.get("harness_id", "")),
        "harness_version": str(metadata.get("version", "")),
        "spec_hash": spec_hash(spec),
    }


def new_harness_id() -> str:
    return f"harness-{uuid4()}"
