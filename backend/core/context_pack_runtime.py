from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.agents.context_pack import build_context_pack
from backend.api.case_memory_store import get_case_memory_store

CONTEXT_PACK_AGENTS = {"writer", "redteam", "legal", "writer_v2", "decision"}


class ContextPackRuntimeProvider:
    """Build and cache one bounded, role-specific pack per run and agent."""

    def build_for_agent(self, state, agent_name: str) -> dict[str, Any] | None:
        if agent_name not in CONTEXT_PACK_AGENTS:
            return None
        snapshots = state.metadata.setdefault("context_pack_snapshots", {})
        if isinstance(snapshots.get(agent_name), dict):
            return deepcopy(snapshots[agent_name])
        try:
            pack = self._build(state, agent_name)
            pack["degraded"] = False
        except Exception as exc:
            pack = {
                "event_facts": {"event_text": state.event, "risk_level": ""},
                "risk_summary": state.event, "fact_status": "", "event_status": "", "risk_level": "",
                "top_public_signals": [], "top_alerts": [], "top_legal_evidence": [],
                "related_case_memories": [], "agent_specific_focus": {"target_agent": agent_name},
                "selected_case_ids": [], "latest_round_summary": None, "dropped_fields": [],
                "safety_notes": [f"ContextPack degraded: {exc.__class__.__name__}"],
                "compression_level": "degraded", "usage_ratio": 0.0, "estimated_chars": 0,
                "token_budget_hint": 3000, "compression_actions": ["context_pack_build_failed"],
                "preserved_fields": ["event_facts", "risk_level"], "aggregate_summary": None,
                "degraded": True,
            }
        pack["context_pack_hash"] = _pack_hash(pack)
        pack["rendered_context"] = _render_pack(pack)
        snapshots[agent_name] = deepcopy(pack)
        state.metadata.setdefault("context_pack_refs", {})[agent_name] = {
            "target_agent": agent_name,
            "context_pack_hash": pack["context_pack_hash"],
            "selected_count": len(pack.get("selected_case_ids", [])),
            "dropped_count": len(pack.get("dropped_fields", [])),
            "compression_level": pack.get("compression_level"),
            "degraded": bool(pack.get("degraded")),
        }
        return deepcopy(pack)

    def _build(self, state, agent_name: str) -> dict[str, Any]:
        results = state.get_all_results()
        sentiment = results.get("sentiment") or {}
        ingestion = state.metadata.get("ingestion") or {}
        event = {
            "event_id": ingestion.get("event_id"), "event_summary": state.event, "title": state.event,
            "company": ingestion.get("company", ""),
            "risk_level": sentiment.get("risk_level") or ingestion.get("risk_level", ""),
            "fact_status": ingestion.get("fact_status", ""), "event_status": ingestion.get("event_status", ""),
            "crisis_type": ingestion.get("crisis_type") or ingestion.get("category", ""),
        }
        evidence = state.metadata.get("legal_evidence") or []
        memories = get_case_memory_store().list_memories(entity_id=ingestion.get("entity_id"), limit=100)
        policy = ((state.metadata.get("harness_spec") or {}).get("context_policy") or {})
        try:
            budget = max(1, int(policy.get("token_budget_hint", policy.get("max_tokens", 3000))))
        except (TypeError, ValueError):
            budget = 3000
        return build_context_pack(
            event=event,
            public_signals=list(ingestion.get("source_items") or [])[:50],
            alerts=[], legal_evidence=evidence, case_memories=memories,
            human_review_notes=list((state.metadata.get("policy") or {}).get("triggers", [])),
            token_budget_hint=budget, target_agent=agent_name,
            compression_mode=str(policy.get("compression_mode", "auto")),
        )


def _pack_hash(pack: dict[str, Any]) -> str:
    stable = {k: v for k, v in pack.items() if k not in {"rendered_context", "context_pack_hash"}}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _render_pack(pack: dict[str, Any]) -> str:
    safe = {k: v for k, v in pack.items() if k not in {"rendered_context", "context_pack_hash"}}
    return json.dumps(safe, ensure_ascii=False, default=str, separators=(",", ":"))


def inject_context_pack(payload: dict[str, Any], pack: dict[str, Any] | None) -> dict[str, Any]:
    if not pack:
        return payload
    enriched = dict(payload)
    enriched["context_pack"] = deepcopy(pack)
    enriched["context_pack_text"] = pack.get("rendered_context", "")
    return enriched
