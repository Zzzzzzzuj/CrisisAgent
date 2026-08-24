from backend.core.reasoning_mode import build_controlled_tool_plan


def test_high_risk_plan_requires_legal_rag_guardrail_and_human_review():
    plan = build_controlled_tool_plan(
        event="某食品品牌被曝光使用过期原料，消费者要求监管介入。",
        sentiment_result={"risk_level": "high"},
        redteam_result={"issues": ["责任表达风险"]},
        available_skills=["legal_rag_search", "guardrail_check"],
    )

    assert plan["reasoning_mode"] == "strict"
    assert "legal_rag_search" in plan["required_tools"]
    assert "guardrail_check" in plan["required_tools"]
    assert plan["human_review_required"] is True
    assert "high_risk" in plan["risk_reasons"]


def test_low_risk_plan_can_skip_legal_rag_with_reason():
    plan = build_controlled_tool_plan(
        event="用户反馈商品包装轻微破损，希望客服处理。",
        sentiment_result={"risk_level": "low"},
        available_skills=["legal_rag_search", "guardrail_check"],
    )

    assert plan["reasoning_mode"] == "fast"
    assert "legal_rag_search" not in plan["required_tools"]
    assert plan["human_review_required"] is False
    assert plan["skipped_tools"][0]["tool"] == "legal_rag_search"
    assert "low_risk" in plan["skipped_tools"][0]["reason"]
