from backend.core.state import AgentState


def evaluate_human_policy(
    state: AgentState,
    evaluation: dict,
    trace_start_index: int = 0,
    include_state_triggers: bool = True,
    include_trace_triggers: bool = True,
) -> dict:
    triggers = []

    if include_state_triggers:
        if _resolve_risk_level(state) == "high":
            triggers.append("high_risk")

        if not evaluation.get("passed", False):
            triggers.append("quality_failed")

        low_score_triggers = _find_low_score_triggers(state)
        triggers.extend(low_score_triggers)
        triggers.extend(_find_guardrail_triggers(state))
        triggers.extend(_find_ingestion_triggers(state))

    if include_trace_triggers:
        triggers.extend(_find_rag_evidence_quality_triggers(state, trace_start_index))
        triggers.extend(_find_llm_fallback_triggers(state, trace_start_index))
        triggers.extend(_find_tool_review_triggers(state, trace_start_index))

    return {
        "required": bool(triggers),
        "reason": _build_reason(triggers),
        "triggers": triggers,
    }


def _resolve_risk_level(state: AgentState) -> str:
    sentiment = state.get_result("sentiment") or {}
    if sentiment.get("risk_level"):
        return str(sentiment["risk_level"]).lower()

    planner_input = state.metadata.get("planner_input", {})
    return str(planner_input.get("risk_level", "")).lower()


def _find_low_score_triggers(state: AgentState) -> list[str]:
    decision = state.get_result("decision") or {}
    scores = decision.get("scores", {})
    triggers = []

    if scores.get("legal_safety", 10) < 7:
        triggers.append("low_legal_safety")
    if scores.get("empathy", 10) < 6:
        triggers.append("low_empathy")
    if scores.get("robustness", 10) < 6:
        triggers.append("low_robustness")

    return triggers


def _find_guardrail_triggers(state: AgentState) -> list[str]:
    guardrails = state.metadata.get("guardrails", {})
    triggers = []
    if (guardrails.get("input") or {}).get("hit"):
        triggers.append("guardrail_input")
    if (guardrails.get("output") or {}).get("hit"):
        triggers.append("guardrail_output")
    return triggers


def _find_ingestion_triggers(state: AgentState) -> list[str]:
    ingestion = state.metadata.get("ingestion", {})
    if not isinstance(ingestion, dict):
        return []

    triggers = []
    if ingestion.get("human_review_required") is True:
        triggers.append("ingestion_review_required")
    if str(ingestion.get("risk_level", "")).lower() == "high":
        triggers.append("ingestion_high_risk")
    if ingestion.get("fact_status") == "unverified":
        triggers.append("ingestion_fact_unverified")
    if ingestion.get("fact_status") == "conflicting":
        triggers.append("ingestion_fact_conflicting")
    if ingestion.get("event_status") == "uncertain":
        triggers.append("ingestion_event_uncertain")
    if ingestion.get("event_status") == "historical" and ingestion.get("human_review_required") is True:
        triggers.append("ingestion_historical_review_required")
    return triggers


def _find_llm_fallback_triggers(state: AgentState, trace_start_index: int = 0) -> list[str]:
    for item in state.trace[max(trace_start_index, 0) :]:
        llm = item.get("llm") if isinstance(item, dict) else None
        if isinstance(llm, dict) and llm.get("fallback_used"):
            return ["llm_fallback"]
    return []


def _find_rag_evidence_quality_triggers(state: AgentState, trace_start_index: int = 0) -> list[str]:
    harness_spec = state.metadata.get("harness_spec") or {}
    review_policy = harness_spec.get("review_policy", {})
    retrieval_policy = harness_spec.get("retrieval_policy", {})
    configured = review_policy.get("triggers", {}) if isinstance(review_policy, dict) else {}
    for item in state.trace[max(trace_start_index, 0) :]:
        rag = item.get("rag") if isinstance(item, dict) else None
        if not isinstance(rag, dict):
            continue
        evidence_quality = rag.get("evidence_quality")
        if (
            isinstance(evidence_quality, dict)
            and evidence_quality.get("should_trigger_human_review") is True
            and retrieval_policy.get("evidence_gate_human_review", True) is not False
            and configured.get("evidence_low_confidence", True) is not False
        ):
            return ["rag_evidence_low_confidence"]
    return []


def _find_tool_review_triggers(state: AgentState, trace_start_index: int = 0) -> list[str]:
    configured = ((state.metadata.get("harness_spec") or {}).get("review_policy", {}) or {}).get("triggers", {})
    mapping = {
        "TOOL_TIMEOUT": ("tool_timeout", "tool_timeout"),
        "TOOL_RETRY_EXHAUSTED": ("tool_retry_exhausted", "tool_retry_exhausted"),
        "TOOL_OUTPUT_INVALID": ("tool_output_invalid", "tool_output_invalid"),
        "TOOL_LOOP_DETECTED": ("tool_loop_detected", "tool_loop_detected"),
    }
    found = []
    for item in state.trace[max(trace_start_index, 0):]:
        if not isinstance(item, dict):
            continue
        candidates = [item.get("error_code")]
        for key in ("tool", "tool_result"):
            value = item.get(key)
            if isinstance(value, dict):
                candidates.append(value.get("error_code"))
        for code in candidates:
            tag_config = mapping.get(str(code or ""))
            if tag_config and configured.get(tag_config[0], True) is not False:
                if tag_config[0] not in found:
                    found.append(tag_config[0])
    return found


def _build_reason(triggers: list[str]) -> str:
    if not triggers:
        return ""
    return "Human review required: " + ", ".join(triggers)
