from __future__ import annotations

from typing import Any

from backend.agents.memory_retriever import retrieve_memories


def build_context_pack(*, event: dict[str, Any] | None = None, event_text: str | None = None,
                       public_signals: list[dict[str, Any]] | None = None,
                       alerts: list[dict[str, Any]] | None = None,
                       legal_evidence: list[dict[str, Any]] | None = None,
                       case_memories: list[dict[str, Any]] | None = None,
                       human_review_notes: list[str] | None = None,
                       token_budget_hint: int = 3000, target_agent: str | None = None) -> dict[str, Any]:
    event = event or {}
    dropped: list[str] = []
    signals = _limited(public_signals or [], 5, "public_signals", dropped)
    alert_values = _limited(alerts or [], 3, "alerts", dropped)
    evidence = _limited(legal_evidence or [], 3, "legal_evidence", dropped)
    ranked_memories = retrieve_memories(event or event_text or "", case_memories or [], top_k=3)
    if len(case_memories or []) > len(ranked_memories):
        dropped.append("case_memories")
    notes = [str(note)[:500] for note in (human_review_notes or [])[:3]]
    if len(human_review_notes or []) > 3:
        dropped.append("human_review_notes")
    safe_memories = [_safe_memory(item) for item in ranked_memories]
    agent_focus = _build_agent_focus(target_agent, safe_memories, event, evidence)
    pack = {
        "event_facts": {
            "event_id": event.get("event_id"),
            "event_text": _clip(event_text or event.get("event_summary") or event.get("title", ""), 500),
            "company": event.get("company", ""),
            "risk_level": event.get("risk_level", ""),
            "fact_status": event.get("fact_status", ""),
            "event_status": event.get("event_status", ""),
        },
        "risk_summary": _clip(event.get("event_summary") or event.get("title", "") or event_text or "", 500),
        "fact_status": event.get("fact_status", ""),
        "event_status": event.get("event_status", ""),
        "top_public_signals": signals,
        "top_alerts": alert_values,
        "top_legal_evidence": evidence,
        "related_case_memories": safe_memories,
        "agent_specific_focus": agent_focus,
        "selected_case_ids": [item.get("memory_id") for item in safe_memories if item.get("memory_id")],
        "latest_round_summary": _latest_round_summary(ranked_memories),
        "human_review_notes": notes,
        "dropped_fields": dropped,
        "token_budget_hint": token_budget_hint,
        "estimated_chars": 0,
    }
    pack["estimated_chars"] = len(str(pack))
    return pack


def _limited(values: list[dict[str, Any]], maximum: int, name: str, dropped: list[str]) -> list[dict[str, Any]]:
    if len(values) > maximum:
        dropped.append(name)
    result = []
    for item in values:
        if not isinstance(item, dict):
            continue
        if item.get("relevant") is False or (
            isinstance(item.get("relevance_score"), (int, float))
            and item["relevance_score"] < 0.2
        ):
            if name not in dropped:
                dropped.append(name)
            continue
        if len(result) >= maximum:
            break
        result.append({
            key: _clip(value, 500) if isinstance(value, str) else value
            for key, value in item.items()
            if key not in {"content", "full_text", "system_prompt", "api_key", "tool_arguments"}
        })
    return result


def _safe_memory(item: dict[str, Any]) -> dict[str, Any]:
    allowed = {"memory_id", "entity_name", "crisis_type", "risk_level", "fact_status",
               "final_statement_summary", "legal_risk_summary", "redteam_summary",
               "response_strategy", "tags", "score", "matched_reasons", "case_group_id", "round_index",
               "previous_memory_id", "previous_statement_summary", "public_reaction_summary",
               "what_changed_since_previous", "previous_redteam_findings", "unresolved_redteam_findings",
               "previous_legal_constraints", "avoid_repeating_points", "outcome"}
    return {key: _clip(value, 500) if isinstance(value, str) else value for key, value in item.items() if key in allowed}


def _build_agent_focus(target_agent: str | None, memories: list[dict[str, Any]], event: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    latest = memories[0] if memories else {}
    redteam = _list_values(memories, "previous_redteam_findings", "redteam_summary")
    unresolved = _list_values(memories, "unresolved_redteam_findings")
    legal = _list_values(memories, "previous_legal_constraints")
    avoid = _list_values(memories, "avoid_repeating_points")
    previous_statement = _first_value(memories, "previous_statement_summary")
    changed = _first_value(memories, "what_changed_since_previous")
    reaction = _first_value(memories, "public_reaction_summary")
    base = {"target_agent": target_agent or "general"}
    if target_agent == "redteam":
        return {**base, "previous_redteam_findings": redteam[:5],
                "unresolved_redteam_findings": unresolved[:5],
                "public_reaction_summary": reaction,
                "already_addressed_issues": [item for item in redteam if item not in unresolved][:5],
                "new_attack_focus": unresolved[:5] or ["检查本轮新增事实、进展和公众反应是否形成新的攻击面"],
                "avoid_repeating_old_attacks": avoid[:5]}
    if target_agent == "legal":
        risk_words = str(event.get("event_summary") or event.get("title") or "")
        return {**base, "previous_legal_constraints": legal[:5],
                "forbidden_promises": legal[:5], "fact_status": event.get("fact_status", ""),
                "event_status": event.get("event_status", ""),
                "top_legal_evidence": evidence[:3],
                "regulatory_sensitivity": "high" if event.get("risk_level") == "high" else "normal",
                "risk_context": _clip(risk_words, 500)}
    if target_agent in {"writer", "writer_v2"}:
        return {**base, "previous_statement_summary": previous_statement,
                "what_changed_since_previous": changed,
                "avoid_repeating_points": avoid[:5],
                "must_address_points": unresolved[:5],
                "tone_guidance": "说明已确认进展和下一步，避免空泛重复承诺"}
    if target_agent == "decision":
        outcomes = [str(item.get("outcome")) for item in memories if item.get("outcome")]
        return {**base, "outcome_trend": outcomes[:3] or ["unknown"],
                "risk_change": changed or "unknown", "unresolved_issues": unresolved[:5],
                "human_review_required_reasons": legal[:5],
                "whether_second_response_needed": bool(unresolved or changed)}
    return {**base, "related_memory_count": len(memories), "latest_round": latest.get("round_index")}


def _list_values(memories: list[dict[str, Any]], *keys: str) -> list[str]:
    values = []
    for memory in memories:
        for key in keys:
            value = memory.get(key)
            if isinstance(value, list):
                values.extend(str(item) for item in value if str(item).strip())
            elif value:
                values.append(str(value))
    return list(dict.fromkeys(values))


def _first_value(memories: list[dict[str, Any]], key: str) -> str | None:
    for memory in memories:
        if memory.get(key):
            return _clip(memory[key], 500)
    return None


def _latest_round_summary(memories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not memories:
        return None
    latest = max(memories, key=lambda item: item.get("round_index") or 0)
    return {"memory_id": latest.get("memory_id"), "round_index": latest.get("round_index"),
            "summary": _clip(latest.get("final_statement_summary", ""), 500),
            "outcome": latest.get("outcome")}


def _clip(value: Any, maximum: int) -> str:
    text = str(value or "")
    if len(text) <= maximum:
        return text
    return text[:max(0, maximum - 3)] + "..." if maximum >= 3 else text[:maximum]
