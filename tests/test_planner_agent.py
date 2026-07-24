from uuid import UUID

from backend.agents import planner_agent


def test_planner_food_safety_high_risk_event_generates_full_plan():
    result = planner_agent.run(
        {
            "event": "某食品品牌被爆使用过期原料，网友要求监管介入。",
            "category": "food_safety",
            "risk_level": "high",
        }
    )

    assert [item["agent"] for item in result["plan"]] == [
        "sentiment",
        "legal",
        "writer",
        "decision",
    ]
    assert result["plan"][0]["confidence"] == 0.9
    assert result["plan"][1]["confidence"] == 0.9


def test_planner_general_low_risk_event_generates_basic_plan():
    result = planner_agent.run(
        {
            "event": "某品牌发布新品活动，用户反馈整体平稳。",
            "category": "general",
            "risk_level": "low",
        }
    )

    assert [item["agent"] for item in result["plan"]] == ["writer", "decision"]


def test_planner_output_schema_is_stable():
    result = planner_agent.run(
        {
            "event": "某App被质疑过度收集用户信息。",
            "category": "data_privacy",
            "risk_level": "medium",
        }
    )

    UUID(result["plan_id"])
    assert set(result.keys()) == {"plan_id", "plan"}
    assert isinstance(result["plan"], list)
    assert result["plan"]

    for item in result["plan"]:
        assert set(item.keys()) == {"agent", "reason", "confidence"}
        assert isinstance(item["agent"], str)
        assert isinstance(item["reason"], str)
        assert isinstance(item["confidence"], float)
        assert 0 <= item["confidence"] <= 1


def test_planner_never_generates_agent_outside_available_agents(monkeypatch):
    monkeypatch.setattr(planner_agent, "EXECUTION_ORDER", ("sentiment", "unknown", "legal", "writer", "decision"))

    result = planner_agent.run(
        {
            "event": "某食品品牌被爆使用过期原料，网友要求监管介入。",
            "category": "food_safety",
            "risk_level": "high",
        }
    )

    agents = [item["agent"] for item in result["plan"]]
    assert "unknown" not in agents
    assert set(agents).issubset(planner_agent.AVAILABLE_AGENTS)
