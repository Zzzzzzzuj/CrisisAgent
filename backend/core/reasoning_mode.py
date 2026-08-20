FAST = "fast"
STANDARD = "standard"
STRICT = "strict"

VALID_REASONING_MODES = {FAST, STANDARD, STRICT}


def select_reasoning_mode(
    *,
    risk_level: str = "",
    guardrail_triggered: bool = False,
    rag_confidence: float | None = None,
    evidence_chunks_count: int = 0,
    llm_fallback_used: bool = False,
    user_requested_strict_review: bool = False,
) -> dict:
    reasons = []
    normalized_risk = str(risk_level or "").lower()

    if user_requested_strict_review:
        reasons.append("user_requested_strict_review")
    if normalized_risk == "high":
        reasons.append("high_risk")
    if guardrail_triggered:
        reasons.append("guardrail_triggered")
    if llm_fallback_used:
        reasons.append("llm_fallback_used")

    low_rag_confidence = (
        rag_confidence is not None
        and evidence_chunks_count > 0
        and float(rag_confidence) < 0.2
    )
    if low_rag_confidence:
        reasons.append("low_rag_confidence")

    if reasons:
        mode = STRICT
        policy = {
            "review_depth": "strict",
            "legal_rag": "force_or_verify",
            "guardrails": "required",
            "human_review": "required",
        }
    elif normalized_risk == "low" and evidence_chunks_count == 0:
        mode = FAST
        reasons.append("low_risk_no_rag_evidence")
        policy = {
            "review_depth": "fast",
            "legal_rag": "skip_if_gate_says_no",
            "guardrails": "basic",
            "human_review": "policy_based",
        }
    else:
        mode = STANDARD
        reasons.append("standard_multi_agent_review")
        policy = {
            "review_depth": "standard",
            "legal_rag": "gate_controlled",
            "guardrails": "required",
            "human_review": "policy_based",
        }

    return {
        "selected_reasoning_mode": mode,
        "reasoning_mode_reason": reasons,
        "recommended_execution_policy": policy,
    }


def reasoning_inputs_from_state(state, user_requested_strict_review: bool = False) -> dict:
    planner_input = state.metadata.get("planner_input", {}) if hasattr(state, "metadata") else {}
    trace = getattr(state, "trace", []) or []
    rag_infos = [
        item.get("rag")
        for item in trace
        if isinstance(item, dict) and isinstance(item.get("rag"), dict)
    ]
    llm_infos = [
        item.get("llm")
        for item in trace
        if isinstance(item, dict) and isinstance(item.get("llm"), dict)
    ]
    guardrails = state.metadata.get("guardrails", {}) if hasattr(state, "metadata") else {}
    guardrail_triggered = any(
        isinstance(result, dict) and result.get("hit")
        for result in guardrails.values()
    ) if isinstance(guardrails, dict) else False

    evidence_chunks_count = 0
    rag_scores = []
    for rag in rag_infos:
        evidence_chunks_count += int(rag.get("evidence_chunks_count") or rag.get("count") or 0)
        for score in rag.get("rerank_scores") or rag.get("scores") or []:
            if isinstance(score, (int, float)):
                rag_scores.append(float(score))

    rag_confidence = max(rag_scores) if rag_scores else None
    llm_fallback_used = any(bool(llm.get("fallback_used")) for llm in llm_infos)

    return {
        "risk_level": planner_input.get("risk_level", ""),
        "guardrail_triggered": guardrail_triggered,
        "rag_confidence": rag_confidence,
        "evidence_chunks_count": evidence_chunks_count,
        "llm_fallback_used": llm_fallback_used,
        "user_requested_strict_review": user_requested_strict_review,
    }


def apply_reasoning_mode_to_state(state, user_requested_strict_review: bool = False) -> dict:
    inputs = reasoning_inputs_from_state(
        state,
        user_requested_strict_review=user_requested_strict_review,
    )
    selection = select_reasoning_mode(**inputs)
    state.metadata["reasoning_mode"] = {
        **selection,
        "inputs": inputs,
    }
    return selection
