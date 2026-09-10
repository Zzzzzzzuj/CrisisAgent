from __future__ import annotations

from typing import Any


def run_memory_eval(context_packs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    packs = context_packs or []
    total = len(packs)
    compliant = sum(1 for pack in packs if len(pack.get("top_public_signals", [])) <= 5
                    and len(pack.get("top_alerts", [])) <= 3
                    and len(pack.get("top_legal_evidence", [])) <= 3
                    and len(pack.get("related_case_memories", [])) <= 3)
    unsafe = sum(_contains_unsafe(pack) for pack in packs)
    distribution: dict[str, int] = {}
    for pack in packs:
        level = str(pack.get("compression_level", "unknown"))
        distribution[level] = distribution.get(level, 0) + 1
    critical_preserved = sum(all(pack.get(field) for field in ("fact_status", "event_status", "risk_level")) for pack in packs)
    trace_complete = sum(_has_drop_trace(pack) for pack in packs)
    focus_metrics = _agent_focus_metrics(packs)
    return {
        "total_cases": total,
        "memory_relevance": round(sum(bool(pack.get("related_case_memories")) for pack in packs) / total, 4) if total else 0.0,
        "context_budget_compliance": round(compliant / total, 4) if total else 1.0,
        "critical_fact_coverage": round(critical_preserved / total, 4) if total else 0.0,
        "unsafe_memory_inclusion_count": unsafe,
        "dropped_noise_count": sum(len(pack.get("dropped_fields", [])) for pack in packs),
        "compression_level_distribution": distribution,
        "over_budget_count": sum(1 for pack in packs if float(pack.get("usage_ratio", 0)) > 1.0),
        "preserved_critical_fields_rate": round(critical_preserved / total, 4) if total else 0.0,
        "dropped_fields_trace_coverage": round(trace_complete / total, 4) if total else 1.0,
        "unsafe_content_leak_count": unsafe,
        "agent_specific_preserved_rate": focus_metrics,
    }


def _contains_unsafe(value: Any) -> int:
    text = str(value).lower()
    return int(any(token in text for token in ("api_key", "system_prompt", "tool_arguments", "full_text")))


def _has_drop_trace(pack: dict[str, Any]) -> bool:
    drops = pack.get("dropped_fields", [])
    return all(isinstance(item, dict) and {"field", "reason", "dropped_count"} <= set(item) for item in drops)


def _agent_focus_metrics(packs: list[dict[str, Any]]) -> dict[str, float]:
    required = {
        "redteam": ("unresolved_redteam_findings", "new_attack_focus"),
        "legal": ("previous_legal_constraints",),
        "writer": ("previous_statement_summary",),
        "writer_v2": ("previous_statement_summary",),
        "decision": ("outcome_trend",),
    }
    results = {}
    for agent, keys in required.items():
        relevant = [pack for pack in packs if pack.get("target_agent") == agent]
        if not relevant:
            results[agent] = 1.0
            continue
        results[agent] = round(sum(any((pack.get("agent_specific_focus") or {}).get(key) is not None for key in keys)
                                   for pack in relevant) / len(relevant), 4)
    return results
