from backend.core.state import AgentState


def evaluate_human_policy(state: AgentState, evaluation: dict) -> dict:
    triggers = []

    if _resolve_risk_level(state) == "high":
        triggers.append("high_risk")

    if not evaluation.get("passed", False):
        triggers.append("quality_failed")

    low_score_triggers = _find_low_score_triggers(state)
    triggers.extend(low_score_triggers)
    triggers.extend(_find_guardrail_triggers(state))
    triggers.extend(_find_llm_fallback_triggers(state))

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


def _find_llm_fallback_triggers(state: AgentState) -> list[str]:
    for item in state.trace:
        llm = item.get("llm") if isinstance(item, dict) else None
        if isinstance(llm, dict) and llm.get("fallback_used"):
            return ["llm_fallback"]
    return []


def _build_reason(triggers: list[str]) -> str:
    if not triggers:
        return ""
    return "Human review required: " + ", ".join(triggers)
