from backend.core.reasoning_mode import (
    FAST,
    STANDARD,
    STRICT,
    apply_reasoning_mode_to_state,
    select_reasoning_mode,
)
from backend.core.state import AgentState


def test_low_risk_without_evidence_selects_fast_mode():
    result = select_reasoning_mode(
        risk_level="low",
        guardrail_triggered=False,
        evidence_chunks_count=0,
        llm_fallback_used=False,
    )

    assert result["selected_reasoning_mode"] == FAST
    assert "low_risk_no_rag_evidence" in result["reasoning_mode_reason"]
    assert result["recommended_execution_policy"]["review_depth"] == "fast"


def test_medium_risk_selects_standard_mode():
    result = select_reasoning_mode(
        risk_level="medium",
        guardrail_triggered=False,
        evidence_chunks_count=2,
        llm_fallback_used=False,
    )

    assert result["selected_reasoning_mode"] == STANDARD
    assert result["recommended_execution_policy"]["legal_rag"] == "gate_controlled"


def test_high_risk_guardrail_or_fallback_selects_strict_mode():
    result = select_reasoning_mode(risk_level="high")

    assert result["selected_reasoning_mode"] == STRICT
    assert "high_risk" in result["reasoning_mode_reason"]
    assert result["recommended_execution_policy"]["human_review"] == "required"

    fallback_result = select_reasoning_mode(risk_level="low", llm_fallback_used=True)
    assert fallback_result["selected_reasoning_mode"] == STRICT
    assert "llm_fallback_used" in fallback_result["reasoning_mode_reason"]

    guardrail_result = select_reasoning_mode(risk_level="low", guardrail_triggered=True)
    assert guardrail_result["selected_reasoning_mode"] == STRICT
    assert "guardrail_triggered" in guardrail_result["reasoning_mode_reason"]


def test_user_requested_strict_review_overrides_fast_mode():
    result = select_reasoning_mode(
        risk_level="low",
        user_requested_strict_review=True,
    )

    assert result["selected_reasoning_mode"] == STRICT
    assert "user_requested_strict_review" in result["reasoning_mode_reason"]


def test_apply_reasoning_mode_reads_state_trace_and_guardrails():
    state = AgentState(session_id="s", plan_id="p", event="event")
    state.metadata["planner_input"] = {"risk_level": "low"}
    state.metadata["guardrails"] = {"input": {"hit": False}}
    state.trace = [
        {
            "agent": "legal",
            "rag": {"count": 1, "rerank_scores": [0.1]},
            "llm": {"fallback_used": True},
        }
    ]

    result = apply_reasoning_mode_to_state(state)

    assert result["selected_reasoning_mode"] == STRICT
    assert state.metadata["reasoning_mode"]["inputs"]["evidence_chunks_count"] == 1
    assert state.metadata["reasoning_mode"]["inputs"]["llm_fallback_used"] is True
