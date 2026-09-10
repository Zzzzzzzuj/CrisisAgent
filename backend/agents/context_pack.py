from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.agents.memory_retriever import retrieve_memories


SENSITIVE_FIELDS = {"content", "full_text", "system_prompt", "api_key", "tool_arguments"}
PRESERVED_FIELDS = ["current_event_facts", "fact_status", "event_status", "risk_level", "agent_specific_focus"]


@dataclass(frozen=True)
class ContextPackCompressionPolicy:
    level: str
    signal_limit: int
    alert_limit: int
    evidence_limit: int
    memory_limit: int
    preview_limit: int
    focus_list_limit: int


POLICIES = {
    "green": ContextPackCompressionPolicy("green", 5, 3, 3, 3, 500, 5),
    "yellow": ContextPackCompressionPolicy("yellow", 5, 3, 3, 3, 350, 5),
    "orange": ContextPackCompressionPolicy("orange", 3, 2, 2, 2, 200, 3),
    "red": ContextPackCompressionPolicy("red", 1, 1, 1, 1, 200, 1),
}


def build_context_pack(*, event: dict[str, Any] | None = None, event_text: str | None = None,
                       public_signals: list[dict[str, Any]] | None = None,
                       alerts: list[dict[str, Any]] | None = None,
                       legal_evidence: list[dict[str, Any]] | None = None,
                       case_memories: list[dict[str, Any]] | None = None,
                       human_review_notes: list[str] | None = None,
                       token_budget_hint: int = 3000, target_agent: str | None = None,
                       compression_mode: str = "auto") -> dict[str, Any]:
    """Build a deterministic preview without changing the Agent workflow."""
    if compression_mode not in {"auto", "off"}:
        raise ValueError("compression_mode must be 'auto' or 'off'.")

    event = event or {}
    drops: list[dict[str, Any]] = []
    signals = _prepare_items(public_signals or [], 5, "public_signals", 500, drops)
    alert_values = _prepare_items(alerts or [], 3, "alerts", 500, drops)
    evidence = _prepare_items(legal_evidence or [], 3, "legal_evidence", 500, drops)
    ranked_memories = retrieve_memories(event or event_text or "", case_memories or [], top_k=3)
    if len(case_memories or []) > len(ranked_memories):
        _record_drop(drops, "case_memories", "baseline_relevance_or_limit", len(case_memories or []) - len(ranked_memories))
    safe_memories = [_safe_memory(item, 500) for item in ranked_memories]
    notes = [_clip(note, 500) for note in (human_review_notes or [])[:3]]
    if len(human_review_notes or []) > 3:
        _record_drop(drops, "human_review_notes", "baseline_limit", len(human_review_notes or []) - 3)

    baseline_focus = _build_agent_focus(target_agent, safe_memories, event, evidence)
    baseline = _make_pack(event, event_text, signals, alert_values, evidence, safe_memories, notes,
                          baseline_focus, drops, token_budget_hint, target_agent)
    pre_compression_chars = _estimate_chars(baseline)
    usage_ratio = round(pre_compression_chars / max(1, token_budget_hint), 4)

    if compression_mode == "off":
        return _finalize(baseline, "off", usage_ratio, pre_compression_chars, ["compression_mode_off"],
                         drops, None, token_budget_hint)

    level = _compression_level(usage_ratio)
    policy = POLICIES[level]
    actions: list[str] = []
    compressed_signals = _apply_item_policy(signals, policy.signal_limit, "public_signals", policy.preview_limit, drops, level)
    compressed_alerts = _apply_item_policy(alert_values, policy.alert_limit, "alerts", policy.preview_limit, drops, level)
    compressed_evidence = _apply_item_policy(evidence, policy.evidence_limit, "legal_evidence", policy.preview_limit, drops, level)
    compressed_memories = _apply_memory_policy(safe_memories, policy, drops)
    if level == "yellow":
        compressed_signals = _limit_per_provider(compressed_signals, 2, drops)
        actions.extend(["low_relevance_signals_filtered", "provider_diversity_limited", "content_preview_truncated_to_350_chars"])
    elif level == "orange":
        actions.extend(["public_signals_limited_to_3", "alerts_limited_to_2", "legal_evidence_limited_to_2",
                        "case_memories_limited_to_2", "content_preview_truncated_to_200_chars",
                        "historical_statements_reduced_to_previous_summary", "similar_signals_aggregated"])
    elif level == "red":
        actions.extend(["minimal_safe_context_only", "public_signals_limited_to_1", "alerts_limited_to_1",
                        "legal_evidence_limited_to_1", "case_memories_limited_to_1", "similar_signals_aggregated"])
    else:
        actions.append("baseline_safety_cleaning_only")

    focus = _compress_agent_focus(target_agent, baseline_focus, policy, event)
    aggregate = _aggregate_summary(public_signals or [], compressed_signals, level)
    pack = _make_pack(event, event_text, compressed_signals, compressed_alerts, compressed_evidence,
                      compressed_memories, notes[:policy.focus_list_limit], focus, drops,
                      token_budget_hint, target_agent)
    return _finalize(pack, level, usage_ratio, pre_compression_chars, actions, drops, aggregate, token_budget_hint)


def _make_pack(event: dict[str, Any], event_text: str | None, signals: list[dict[str, Any]],
               alerts: list[dict[str, Any]], evidence: list[dict[str, Any]], memories: list[dict[str, Any]],
               notes: list[str], focus: dict[str, Any], drops: list[dict[str, Any]], token_budget_hint: int,
               target_agent: str | None) -> dict[str, Any]:
    return {
        "event_facts": {"event_id": event.get("event_id"),
                        "event_text": _clip(event_text or event.get("event_summary") or event.get("title", ""), 500),
                        "company": event.get("company", ""), "risk_level": event.get("risk_level", ""),
                        "fact_status": event.get("fact_status", ""), "event_status": event.get("event_status", "")},
        "risk_summary": _clip(event.get("event_summary") or event.get("title") or event_text or "", 500),
        "fact_status": event.get("fact_status", ""), "event_status": event.get("event_status", ""),
        "risk_level": event.get("risk_level", ""), "top_public_signals": signals, "top_alerts": alerts,
        "top_legal_evidence": evidence, "related_case_memories": memories, "agent_specific_focus": focus,
        "selected_case_ids": [item.get("memory_id") for item in memories if item.get("memory_id")],
        "latest_round_summary": _latest_round_summary(memories), "human_review_notes": notes,
        "target_agent": target_agent or "general", "token_budget_hint": token_budget_hint, "dropped_fields": drops,
    }


def _finalize(pack: dict[str, Any], level: str, usage_ratio: float, pre_chars: int,
              actions: list[str], drops: list[dict[str, Any]], aggregate: str | None,
              token_budget_hint: int) -> dict[str, Any]:
    safety_notes = ["Deterministic preview only; no LLM call.",
                    "Full news text, system prompts, API keys, and tool arguments are excluded."]
    if level == "red":
        safety_notes.append("ContextPack was aggressively compressed; human review is recommended for high-risk response.")
    pack.update({"compression_level": level, "usage_ratio": usage_ratio,
                 "pre_compression_estimated_chars": pre_chars, "estimated_chars": _estimate_chars(pack),
                 "token_budget_hint": token_budget_hint, "compression_actions": actions,
                 "aggregate_summary": aggregate, "preserved_fields": PRESERVED_FIELDS,
                 "dropped_fields": drops, "dropped_field_names": [item["field"] for item in drops],
                 "safety_notes": safety_notes})
    return pack


def _compression_level(usage_ratio: float) -> str:
    if usage_ratio <= 0.60:
        return "green"
    if usage_ratio <= 0.75:
        return "yellow"
    if usage_ratio <= 0.90:
        return "orange"
    return "red"


def _prepare_items(values: list[dict[str, Any]], maximum: int, name: str, clip_limit: int,
                   drops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = [item for item in values if isinstance(item, dict)]
    relevant = [item for item in valid if not _is_low_relevance(item)]
    if len(relevant) < len(valid):
        _record_drop(drops, name, "low_relevance", len(valid) - len(relevant))
    ranked = _diversify_providers(sorted(relevant, key=_item_priority, reverse=True))
    if len(ranked) > maximum:
        _record_drop(drops, name, "baseline_limit", len(ranked) - maximum)
    return [_sanitize_item(item, clip_limit) for item in ranked[:maximum]]


def _apply_item_policy(items: list[dict[str, Any]], maximum: int, name: str, clip_limit: int,
                       drops: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    if len(items) > maximum:
        _record_drop(drops, name, f"exceeded_{level}_waterline", len(items) - maximum)
    return [_sanitize_item(item, clip_limit) for item in items[:maximum]]


def _apply_memory_policy(memories: list[dict[str, Any]], policy: ContextPackCompressionPolicy,
                         drops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(memories) > policy.memory_limit:
        _record_drop(drops, "case_memories", f"exceeded_{policy.level}_waterline", len(memories) - policy.memory_limit)
    result = []
    for item in memories[:policy.memory_limit]:
        if policy.level in {"orange", "red"}:
            compact = {key: item.get(key) for key in ("memory_id", "entity_name", "crisis_type", "risk_level",
                       "fact_status", "case_group_id", "round_index", "previous_statement_summary", "score",
                       "matched_reasons", "outcome") if item.get(key) is not None}
            result.append(compact)
        else:
            result.append(_safe_memory(item, policy.preview_limit))
    return result


def _limit_per_provider(items: list[dict[str, Any]], maximum: int, drops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    kept = []
    removed = 0
    for item in items:
        provider = str(item.get("provider") or item.get("source") or "unknown")
        counts[provider] = counts.get(provider, 0) + 1
        if counts[provider] > maximum:
            removed += 1
            continue
        kept.append(item)
    if removed:
        _record_drop(drops, "public_signals", "provider_diversity_limit", removed)
    return kept


def _compress_agent_focus(target_agent: str | None, focus: dict[str, Any], policy: ContextPackCompressionPolicy,
                          event: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "redteam": ["previous_redteam_findings", "unresolved_redteam_findings", "new_attack_focus", "public_reaction_summary", "avoid_repeating_old_attacks"],
        "legal": ["previous_legal_constraints", "forbidden_promises", "fact_status", "event_status", "top_legal_evidence", "regulatory_sensitivity"],
        "writer": ["previous_statement_summary", "what_changed_since_previous", "avoid_repeating_points", "must_address_points", "tone_guidance"],
        "writer_v2": ["previous_statement_summary", "what_changed_since_previous", "avoid_repeating_points", "must_address_points", "tone_guidance"],
        "decision": ["outcome_trend", "risk_change", "unresolved_issues", "human_review_required_reasons", "whether_second_response_needed"],
        "sentiment": ["current_event_facts", "top_public_signals", "matched_keywords", "risk_level", "public_reaction_summary"],
    }
    agent = target_agent or "general"
    if agent == "sentiment":
        focus = {**focus, "current_event_facts": event.get("event_summary") or event.get("title", ""),
                 "top_public_signals": [], "matched_keywords": event.get("risk_keywords", []),
                 "risk_level": event.get("risk_level", "")}
    allowed = key_map.get(agent)
    if not allowed or policy.level in {"green", "yellow"}:
        return _limit_focus_lists(focus, policy.focus_list_limit, policy.preview_limit)
    compact = {"target_agent": focus.get("target_agent", agent)}
    for key in allowed:
        if key in focus:
            compact[key] = _compact_focus_value(focus[key], policy.focus_list_limit, policy.preview_limit)
    return compact


def _limit_focus_lists(focus: dict[str, Any], list_limit: int, clip_limit: int) -> dict[str, Any]:
    return {key: _compact_focus_value(value, list_limit, clip_limit) for key, value in focus.items()}


def _compact_focus_value(value: Any, list_limit: int, clip_limit: int) -> Any:
    if isinstance(value, list):
        return [_compact_focus_value(item, list_limit, clip_limit) for item in value[:list_limit]]
    if isinstance(value, dict):
        return {key: _compact_focus_value(item, list_limit, clip_limit) for key, item in value.items() if key not in SENSITIVE_FIELDS}
    if isinstance(value, str):
        return _clip(value, clip_limit)
    return value


def _aggregate_summary(original: list[dict[str, Any]], retained: list[dict[str, Any]], level: str) -> str | None:
    if level not in {"orange", "red"} or len(original) <= len(retained):
        return None
    omitted = len(original) - len(retained)
    providers = sorted({str(item.get("provider") or item.get("source") or "unknown") for item in original})[:3]
    keywords = []
    for item in original:
        keywords.extend(str(value) for value in item.get("risk_keywords", [])[:3])
    keyword_text = "、".join(list(dict.fromkeys(keywords))[:3]) or "未标注风险词"
    return f"另有 {omitted} 条相似来源被压缩；来源：{'、'.join(providers)}；最高风险关键词：{keyword_text}。"


def _is_low_relevance(item: dict[str, Any]) -> bool:
    return item.get("relevant") is False or (isinstance(item.get("relevance_score"), (int, float)) and item["relevance_score"] < 0.2)


def _item_priority(item: dict[str, Any]) -> tuple[float, int, str]:
    relevance = float(item.get("relevance_score", 0.5)) if isinstance(item.get("relevance_score", 0.5), (int, float)) else 0.5
    risk = {"high": 3, "medium": 2, "low": 1}.get(str(item.get("risk_level", "")).lower(), 0)
    return relevance, risk, str(item.get("published_at") or item.get("created_at") or "")


def _diversify_providers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-ranked item per source near the front before repeats."""
    first_pass: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        provider = str(item.get("provider") or item.get("source") or "unknown")
        if provider in seen:
            repeats.append(item)
        else:
            seen.add(provider)
            first_pass.append(item)
    return first_pass + repeats


def _sanitize_item(item: dict[str, Any], clip_limit: int) -> dict[str, Any]:
    return {key: _compact_focus_value(value, 5, clip_limit) for key, value in item.items() if key not in SENSITIVE_FIELDS}


def _safe_memory(item: dict[str, Any], clip_limit: int) -> dict[str, Any]:
    allowed = {"memory_id", "entity_name", "crisis_type", "risk_level", "fact_status", "final_statement_summary",
               "legal_risk_summary", "redteam_summary", "response_strategy", "tags", "score", "matched_reasons",
               "case_group_id", "round_index", "previous_memory_id", "previous_statement_summary",
               "public_reaction_summary", "what_changed_since_previous", "previous_redteam_findings",
               "unresolved_redteam_findings", "previous_legal_constraints", "avoid_repeating_points", "outcome"}
    return {key: _compact_focus_value(value, 5, clip_limit) for key, value in item.items() if key in allowed}


def _build_agent_focus(target_agent: str | None, memories: list[dict[str, Any]], event: dict[str, Any],
                       evidence: list[dict[str, Any]]) -> dict[str, Any]:
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
        return {**base, "previous_redteam_findings": redteam[:5], "unresolved_redteam_findings": unresolved[:5],
                "public_reaction_summary": reaction, "already_addressed_issues": [item for item in redteam if item not in unresolved][:5],
                "new_attack_focus": unresolved[:5] or ["检查本轮新增事实、进展和公众反应是否形成新的攻击面"], "avoid_repeating_old_attacks": avoid[:5]}
    if target_agent == "legal":
        return {**base, "previous_legal_constraints": legal[:5], "forbidden_promises": legal[:5],
                "fact_status": event.get("fact_status", ""), "event_status": event.get("event_status", ""),
                "top_legal_evidence": evidence[:3], "regulatory_sensitivity": "high" if event.get("risk_level") == "high" else "normal"}
    if target_agent in {"writer", "writer_v2"}:
        return {**base, "previous_statement_summary": previous_statement, "what_changed_since_previous": changed,
                "avoid_repeating_points": avoid[:5], "must_address_points": unresolved[:5],
                "tone_guidance": "说明已确认进展和下一步，避免空泛重复承诺"}
    if target_agent == "decision":
        outcomes = [str(item.get("outcome")) for item in memories if item.get("outcome")]
        return {**base, "outcome_trend": outcomes[:3] or ["unknown"], "risk_change": changed or "unknown",
                "unresolved_issues": unresolved[:5], "human_review_required_reasons": legal[:5],
                "whether_second_response_needed": bool(unresolved or changed)}
    return {**base, "related_memory_count": len(memories), "latest_round": latest.get("round_index")}


def _record_drop(drops: list[dict[str, Any]], field: str, reason: str, count: int) -> None:
    if count > 0:
        drops.append({"field": field, "reason": reason, "dropped_count": count})


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
            "summary": _clip(latest.get("previous_statement_summary") or latest.get("final_statement_summary", ""), 500),
            "outcome": latest.get("outcome")}


def _estimate_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _clip(value: Any, maximum: int) -> str:
    text = str(value or "")
    if len(text) <= maximum:
        return text
    return text[:max(0, maximum - 3)] + "..." if maximum >= 3 else text[:maximum]
