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
    for item in state.trace[max(trace_start_index, 0) :]:
        rag = item.get("rag") if isinstance(item, dict) else None
        if not isinstance(rag, dict):
            continue
        evidence_quality = rag.get("evidence_quality")
        if (
            isinstance(evidence_quality, dict)
            and evidence_quality.get("should_trigger_human_review") is True
        ):
            return ["rag_evidence_low_confidence"]
    return []


def _build_reason(triggers: list[str]) -> str:
    if not triggers:
        return ""
    return "Human review required: " + ", ".join(triggers)
