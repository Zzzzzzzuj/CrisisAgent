from backend.core.tool_policy import evaluate_tool_call_policy, validate_tool_plan_safety


def test_high_risk_plan_cannot_skip_required_tools():
    result = validate_tool_plan_safety(
        {
            "risk_level": "high",
            "required_tools": ["guardrail_check"],
        }
    )

    assert result["allow"] is False
    assert "legal_rag_search" in result["reason"]


def test_sensitive_action_is_denied_for_llm_tool_call():
    result = evaluate_tool_call_policy("approve", {"session_id": "s"})

    assert result["allow"] is False
    assert result["reason"] == "sensitive_action_must_not_be_called_by_llm"


def test_tool_arguments_must_be_object():
    result = evaluate_tool_call_policy("legal_rag_search", "query")

    assert result["allow"] is False
    assert result["reason"] == "tool_arguments_must_be_object"


def test_normal_tool_call_is_allowed():
    result = evaluate_tool_call_policy(
        "guardrail_check",
        {"event": "食品安全事件"},
        {"risk_level": "low", "required_tools": ["guardrail_check"]},
    )

    assert result["allow"] is True
