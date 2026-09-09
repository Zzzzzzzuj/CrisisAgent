from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def retrieve_memories(query: str | dict[str, Any], memories: list[dict[str, Any]], *, top_k: int = 3) -> list[dict[str, Any]]:
    fields = _query_fields(query)
    ranked = []
    for memory in memories:
        if memory.get("archived", False):
            continue
        score, reasons = _score(fields, memory)
        if score > 0:
            ranked.append({**memory, "score": round(score, 4), "matched_reasons": reasons})
    ranked.sort(key=lambda item: (-item["score"], str(item.get("memory_id", ""))))
    return ranked[:max(0, top_k)]


class MemoryRetriever:
    def retrieve(self, query: str | dict[str, Any], memories: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
        return retrieve_memories(query, memories, top_k=top_k)


def _query_fields(query: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(query, dict):
        return {
            "entity": _tokens(query.get("entity_name") or query.get("company")),
            "type": str(query.get("crisis_type") or query.get("category") or "").lower(),
            "risk": str(query.get("risk_level") or "").lower(),
            "fact": str(query.get("fact_status") or "").lower(),
            "tags": _tokens(query.get("tags") or query.get("risk_keywords") or query.get("event")),
            "case_group_id": query.get("case_group_id"),
            "round_index": query.get("round_index"),
        }
    return {"entity": set(), "type": "", "risk": "", "fact": "", "tags": _tokens(query),
            "case_group_id": None, "round_index": None}


def _score(fields: dict[str, Any], memory: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if fields["entity"] & _tokens(memory.get("entity_name")):
        score += 0.4
        reasons.append("entity_match")
    if fields["type"] and fields["type"] == str(memory.get("crisis_type", "")).lower():
        score += 0.25
        reasons.append("crisis_type_match")
    if fields["risk"] and fields["risk"] == str(memory.get("risk_level", "")).lower():
        score += 0.1
        reasons.append("risk_level_match")
    if fields["fact"] and fields["fact"] == str(memory.get("fact_status", "")).lower():
        score += 0.05
        reasons.append("fact_status_match")
    if fields["tags"] & _tokens(memory.get("tags", [])):
        score += min(0.15, 0.05 * len(fields["tags"] & _tokens(memory.get("tags", []))))
        reasons.append("tag_overlap")
    if fields["tags"] & _tokens(" ".join(str(memory.get(key, "")) for key in ("response_strategy", "legal_risk_summary", "redteam_summary"))):
        score += 0.05
        reasons.append("risk_keyword_overlap")
    if fields.get("case_group_id") and fields["case_group_id"] == memory.get("case_group_id"):
        score += 0.35
        reasons.append("case_group_match")
    if fields.get("round_index") is not None and memory.get("round_index") is not None:
        try:
            distance = abs(int(fields["round_index"]) - int(memory["round_index"]))
        except (TypeError, ValueError):
            distance = None
        if distance is None:
            return _score_without_round_bonus(fields, memory, score, reasons)
        if distance <= 1:
            score += 0.18
            reasons.append("nearby_round")
        elif distance <= 3:
            score += 0.08
            reasons.append("related_round")
    if str(memory.get("outcome", "")).lower() == "worsened":
        score += 0.08
        reasons.append("worsened_outcome")
    lifecycle_text = " ".join(str(memory.get(key, "")) for key in (
        "unresolved_redteam_findings", "previous_legal_constraints"
    ))
    if fields["tags"] & _tokens(lifecycle_text):
        score += 0.1
        reasons.append("unresolved_lifecycle_overlap")
    created = _parse_date(memory.get("created_at"))
    if created and (datetime.utcnow() - created).days < 90:
        score += 0.02
        reasons.append("recent_memory")
    return score, reasons


def _score_without_round_bonus(fields: dict[str, Any], memory: dict[str, Any], score: float,
                               reasons: list[str]) -> tuple[float, list[str]]:
    """Keep legacy records with non-numeric round values searchable."""
    if str(memory.get("outcome", "")).lower() == "worsened":
        score += 0.08
        reasons.append("worsened_outcome")
    return score, reasons


def _tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return {token.lower() for token in re.findall(r"[w一-鿿]+", str(value or ""))}


def _parse_date(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
