from __future__ import annotations

from typing import Any


_CONTENT_KEYS = {
    "claim", "content", "context_pack", "context_pack_text", "draft", "event",
    "evidence_text", "full_text", "history", "messages", "prompt", "query",
    "rendered_context", "response_text", "retrieval_query", "text", "text_preview",
    "tool_arguments",
}
_SAFE_STRING_KEYS = {
    "action", "agent", "category", "claim_extraction_status", "compression_level",
    "error_code", "fact_status", "mode", "retrieval_status", "risk_level", "severity",
    "status", "stop_reason", "target_agent", "tool_name",
}


def context_pack_trace_metadata(pack: dict[str, Any]) -> dict[str, Any]:
    event_facts = pack.get("event_facts") if isinstance(pack.get("event_facts"), dict) else {}
    sections = (
        "event_facts", "risk_summary", "top_public_signals", "top_alerts",
        "top_legal_evidence", "related_case_memories", "agent_specific_focus",
        "human_review_notes",
    )
    selected = [name for name in sections if _has_value(pack.get(name))]
    event_fact_count = sum(_has_value(value) for value in event_facts.values())
    digest = str(pack.get("context_pack_hash", ""))
    chars_before = _safe_nonnegative_int(pack.get("pre_compression_estimated_chars"))
    chars_after = len(str(pack.get("rendered_context", "")))
    return {
        "context_pack_id": f"cp_{digest[:16]}" if digest else None,
        "role": pack.get("target_agent", "general"),
        "context_chars": chars_after,
        "chars_before": chars_before,
        "chars_after": chars_after,
        "reduction_chars": chars_before - chars_after if chars_before is not None and chars_after is not None else None,
        "reduction_ratio": round((chars_before - chars_after) / chars_before, 4)
        if chars_before not in (None, 0) and chars_after is not None else None,
        "selected_sections": selected,
        "fact_count": event_fact_count,
        "evidence_count": len(pack.get("top_legal_evidence", [])) if isinstance(pack.get("top_legal_evidence"), list) else 0,
        "budget": pack.get("token_budget_hint"),
        "budget_chars": pack.get("token_budget_hint") if pack.get("budget_unit") == "characters" else None,
        "truncated": bool(pack.get("dropped_fields")),
    }


def _safe_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def summarize_trace_input(value: Any) -> dict[str, Any]:
    summary = _shape_summary(value)
    if isinstance(value, dict) and isinstance(value.get("context_pack"), dict):
        summary["context_pack"] = context_pack_trace_metadata(value["context_pack"])
    return summary


def summarize_trace_output(value: Any) -> dict[str, Any]:
    summary = _shape_summary(value)
    if isinstance(value, dict):
        safe = {key: item for key, item in value.items()
                if key in _SAFE_STRING_KEYS and isinstance(item, (str, bool, int, float))}
        if safe:
            summary["safe_signals"] = safe
    return summary


def summarize_skill_trace(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _shape_summary(value)
    results = []
    for item in value.get("results", []):
        if not isinstance(item, dict):
            continue
        results.append({key: item[key] for key in (
            "tool_name", "skill_id", "success", "error_code", "attempts", "retry_count",
            "fallback_used", "human_review_required", "trace",
        ) if key in item})
    return {
        "selected": value.get("selected", []),
        "skipped": value.get("skipped", []),
        "results": results,
        "failure_tags": value.get("failure_tags", []),
    }


def sanitize_trace_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"query", "retrieval_query"} and isinstance(item, str):
                cleaned[f"{lowered}_chars"] = len(item)
                continue
            if lowered in _CONTENT_KEYS:
                continue
            if lowered in {"legal_claims", "claims"} and isinstance(item, list):
                cleaned["claim_summaries"] = [
                    {field: claim[field] for field in (
                        "requires_legal_rule", "requires_case_fact", "claim_origin",
                    ) if field in claim}
                    for claim in item if isinstance(claim, dict)
                ]
                continue
            cleaned[key] = sanitize_trace_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_trace_metadata(item) for item in value]
    return value


def _shape_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        fields = sorted(str(key) for key in value if str(key).lower() not in _CONTENT_KEYS)
        lengths: dict[str, int] = {}
        counts: dict[str, int] = {}
        _collect_shape(value, "", lengths, counts)
        return {"fields": fields, "text_chars": lengths, "collection_counts": counts}
    if isinstance(value, str):
        return {"type": "text", "text_chars": len(value)}
    return {"type": type(value).__name__}


def _collect_shape(value: Any, path: str, lengths: dict[str, int], counts: dict[str, int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _CONTENT_KEYS:
                if isinstance(item, str):
                    lengths[f"{path}.{key}".strip(".")] = len(item)
                elif isinstance(item, (list, dict)):
                    counts[f"{path}.{key}".strip(".")] = len(item)
                continue
            _collect_shape(item, f"{path}.{key}".strip("."), lengths, counts)
    elif isinstance(value, list):
        counts[path or "items"] = len(value)
        for index, item in enumerate(value):
            _collect_shape(item, f"{path}[{index}]", lengths, counts)
    elif isinstance(value, str):
        lengths[path or "value"] = len(value)


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}
