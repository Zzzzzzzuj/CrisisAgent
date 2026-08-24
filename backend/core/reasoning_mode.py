FAST = "fast"
STANDARD = "standard"
STRICT = "strict"

VALID_REASONING_MODES = {FAST, STANDARD, STRICT}
HIGH_RISK_REQUIRED_TOOLS = ("legal_rag_search", "guardrail_check")


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


def build_controlled_tool_plan(
    *,
    event: str,
    sentiment_result: dict | None = None,
    redteam_result: dict | None = None,
    available_skills: list[str] | None = None,
    user_requested_strict_review: bool = False,
) -> dict:
    sentiment_result = sentiment_result or {}
    available = set(available_skills or [])
    risk_level = str(sentiment_result.get("risk_level") or _infer_risk_level(event)).lower()
    risk_reasons = _risk_reasons(event, risk_level, redteam_result or {})
    reasoning = select_reasoning_mode(
        risk_level=risk_level,
        guardrail_triggered=False,
        evidence_chunks_count=0,
        llm_fallback_used=False,
        user_requested_strict_review=user_requested_strict_review,
    )

    required_agents = ["legal"]
    required_tools = []
    skipped_tools = []
    validation_notes = []

    if risk_level == "high" or reasoning["selected_reasoning_mode"] == STRICT:
        for tool in HIGH_RISK_REQUIRED_TOOLS:
            required_tools.append(tool)
            if available and tool not in available:
                validation_notes.append(f"required_tool_unavailable:{tool}")
        human_review_required = True
    elif risk_level == "low":
        human_review_required = False
        if "guardrail_check" in available or not available:
            required_tools.append("guardrail_check")
        skipped_tools.append(
            {
                "tool": "legal_rag_search",
                "reason": "low_risk_case_can_skip_legal_rag_search",
            }
        )
    else:
        human_review_required = False
        required_tools.append("guardrail_check")
        if "legal_rag_search" in available or not available:
            required_tools.append("legal_rag_search")

    if "knowledge_document_search" in available and risk_level in {"high", "medium"}:
        required_tools.append("knowledge_document_search")

    return {
        "reasoning_mode": reasoning["selected_reasoning_mode"],
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "required_agents": required_agents,
        "required_tools": _unique(required_tools),
        "skipped_tools": skipped_tools,
        "human_review_required": human_review_required,
        "validation_notes": validation_notes,
        "recommended_execution_policy": reasoning["recommended_execution_policy"],
    }


def _infer_risk_level(event: str) -> str:
    if any(term in str(event) for term in ("监管", "泄露", "过期", "抵制", "热搜", "违法", "召回")):
        return "high"
    if any(term in str(event) for term in ("质疑", "投诉", "传播", "担心", "不适")):
        return "medium"
    return "low"


def _risk_reasons(event: str, risk_level: str, redteam_result: dict) -> list[str]:
    reasons = []
    if risk_level == "high":
        reasons.append("high_risk")
    if any(term in str(event) for term in ("监管", "违法", "责任")):
        reasons.append("legal_or_regulatory_signal")
    if any(term in str(event) for term in ("泄露", "过期", "召回", "不适")):
        reasons.append("public_harm_signal")
    if redteam_result.get("issues") or redteam_result.get("suggestions"):
        reasons.append("redteam_review_has_findings")
    return reasons or ["low_or_unclear_risk"]


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
