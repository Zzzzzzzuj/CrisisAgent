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
    return {
        "total_cases": total,
        "memory_relevance": round(sum(bool(pack.get("related_case_memories")) for pack in packs) / total, 4) if total else 0.0,
        "context_budget_compliance": round(compliant / total, 4) if total else 1.0,
        "critical_fact_coverage": round(sum(bool(pack.get("fact_status")) for pack in packs) / total, 4) if total else 0.0,
        "unsafe_memory_inclusion_count": unsafe,
        "dropped_noise_count": sum(len(pack.get("dropped_fields", [])) for pack in packs),
    }


def _contains_unsafe(value: Any) -> int:
    text = str(value).lower()
    return int(any(token in text for token in ("api_key", "system_prompt", "tool_arguments", "full_text")))
