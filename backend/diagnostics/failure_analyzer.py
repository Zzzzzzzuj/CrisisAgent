from __future__ import annotations

from typing import Any


FAILURE_AREAS = {
    "retrieval_not_needed": "retrieval_policy",
    "retrieval_low_quality": "retrieval_policy",
    "evidence_low_confidence": "retrieval_policy",
    "evidence_conflict": "retrieval_policy",
    "tool_timeout": "tools_policy",
    "tool_retry_exhausted": "tools_policy",
    "tool_output_invalid": "tools_policy",
    "tool_loop_detected": "tools_policy",
    "context_over_budget": "context_policy",
    "context_critical_field_dropped": "context_policy",
    "review_required": "review_policy",
    "review_scope_mismatch": "review_policy",
}


def analyze_trace_failure(
    trace: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | Any | None = None,
    review: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    context_pack: dict[str, Any] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trace = trace or _value(state, "trace", []) or []
    tags: list[str] = []
    evidence_refs: list[str] = []
    related_trace_ids: list[str] = []
    details: list[str] = []

    for index, item in enumerate(trace):
        if not isinstance(item, dict):
            continue
        trace_id = str(item.get("trace_id") or item.get("id") or f"trace-{index}")
        rag = item.get("rag") if isinstance(item.get("rag"), dict) else {}
        quality = rag.get("evidence_quality") if isinstance(rag.get("evidence_quality"), dict) else {}
        if rag.get("retrieval_skipped") is True:
            _add(tags, "retrieval_not_needed")
            related_trace_ids.append(trace_id)
        if quality.get("low_confidence") is True or quality.get("quality") == "low":
            _add(tags, "evidence_low_confidence")
            related_trace_ids.append(trace_id)
        if quality.get("context_pollution_rate", 0) and quality.get("context_pollution_rate", 0) > 0.5:
            _add(tags, "retrieval_low_quality")
            related_trace_ids.append(trace_id)
        if any(reason in {"source_category_mismatch", "high_context_pollution"} for reason in quality.get("reasons", [])):
            _add(tags, "evidence_conflict")
        for chunk in rag.get("evidence_chunks") or rag.get("chunks") or []:
            if isinstance(chunk, dict):
                ref = chunk.get("chunk_id") or chunk.get("source") or chunk.get("id")
                if ref:
                    evidence_refs.append(str(ref))
        if item.get("status") == "failed":
            error_text = str(item.get("error") or "").lower()
            if "timeout" in error_text:
                _add(tags, "tool_timeout")

        compact = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else item.get("tool")
        _add_tool_error(tags, compact)
        _add_tool_error(tags, item.get("error_code"))

    for result in tool_results or []:
        _add_tool_error(tags, result)

    pack = context_pack or _value(state, "context_pack", {}) or {}
    if isinstance(pack, dict):
        if pack.get("compression_level") in {"orange", "red"} or pack.get("usage_ratio", 0) > 0.9:
            _add(tags, "context_over_budget")
        dropped = pack.get("dropped_fields") or pack.get("dropped_field_names") or []
        critical = {"fact_status", "event_status", "risk_level", "target_agent"}
        if any(str(item.get("field") if isinstance(item, dict) else item) in critical for item in dropped):
            _add(tags, "context_critical_field_dropped")

    review = review or _value(state, "approval", {}) or {}
    if isinstance(review, dict) and (review.get("required") is True or review.get("human_review_required") is True):
        _add(tags, "review_required")
    if isinstance(review, dict) and review.get("scope_mismatch") is True:
        _add(tags, "review_scope_mismatch")

    severity = "none" if not tags else "high" if any(tag in {"evidence_conflict", "tool_loop_detected", "review_scope_mismatch", "context_critical_field_dropped"} for tag in tags) else "medium"
    areas = sorted({FAILURE_AREAS[tag] for tag in tags})
    return {
        "failure_tags": tags,
        "severity": severity,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "related_trace_ids": list(dict.fromkeys(related_trace_ids)),
        "diagnosis_summary": "No deterministic failure detected." if not tags else "Detected: " + ", ".join(tags),
        "recommended_harness_areas": areas,
    }


def _add(tags: list[str], value: str) -> None:
    if value not in tags:
        tags.append(value)


def _add_tool_error(tags: list[str], value: Any) -> None:
    if isinstance(value, dict):
        value = value.get("error_code") or value.get("error")
    normalized = str(value or "")
    mapping = {
        "TOOL_TIMEOUT": "tool_timeout",
        "TOOL_RETRY_EXHAUSTED": "tool_retry_exhausted",
        "TOOL_OUTPUT_INVALID": "tool_output_invalid",
        "TOOL_LOOP_DETECTED": "tool_loop_detected",
    }
    if normalized in mapping:
        _add(tags, mapping[normalized])


def _value(source: Any, key: str, default: Any) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default) if source is not None else default
