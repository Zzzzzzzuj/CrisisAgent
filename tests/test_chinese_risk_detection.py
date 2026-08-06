from backend.agents import sentiment_agent
from backend.core.dynamic_runtime import _infer_category, _infer_risk_level
from backend.core.policy import evaluate_human_policy
from backend.core.state import AgentState


FOOD_SAFETY_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。"
LOW_RISK_COMPLAINT = "用户反馈商品包装轻微破损，希望客服处理。"


def test_chinese_food_safety_event_is_detected_as_high_risk(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")

    result = sentiment_agent.run(FOOD_SAFETY_EVENT)

    assert result["risk_level"] == "high"
    assert result["public_emotion"] == "angry"
    assert "过期原料" in result["keywords"]
    assert "监管介入" in result["keywords"]


def test_dynamic_runtime_infers_food_safety_and_high_risk():
    assert _infer_category(FOOD_SAFETY_EVENT) == "food_safety"
    assert _infer_risk_level(FOOD_SAFETY_EVENT) == "high"


def test_high_risk_chinese_event_requires_human_gate():
    state = AgentState(
        session_id="test-chinese-high-risk",
        plan_id="test-plan",
        event=FOOD_SAFETY_EVENT,
        metadata={"planner_input": {"category": "food_safety", "risk_level": "high"}},
    )
    state.set_result("sentiment", {"risk_level": "high"})

    policy = evaluate_human_policy(
        state,
        {
            "passed": True,
            "quality_scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )

    assert policy["required"] is True
    assert "high_risk" in policy["reason"]


def test_low_risk_chinese_complaint_does_not_trigger_high_risk_human_gate(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    sentiment = sentiment_agent.run(LOW_RISK_COMPLAINT)
    risk_level = _infer_risk_level(LOW_RISK_COMPLAINT)
    state = AgentState(
        session_id="test-chinese-low-risk",
        plan_id="test-plan",
        event=LOW_RISK_COMPLAINT,
        metadata={"planner_input": {"category": _infer_category(LOW_RISK_COMPLAINT), "risk_level": risk_level}},
    )
    state.set_result("sentiment", {"risk_level": risk_level})

    policy = evaluate_human_policy(
        state,
        {
            "passed": True,
            "quality_scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )

    assert sentiment["risk_level"] != "high"
    assert risk_level != "high"
    assert policy["required"] is False
