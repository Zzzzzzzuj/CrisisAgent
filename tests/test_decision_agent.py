from backend.agents import decision_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "second_draft": (
        "我们已注意到相关传播内容，并充分理解公众担忧。"
        "公司已启动专项核查，并将配合监管、持续同步进展。"
        "对于给消费者带来的不安，我们表示歉意。"
    ),
    "sentiment_analysis": {
        "risk_level": "high",
        "public_emotion": "angry",
        "keywords": ["过期原料", "监管介入"],
        "recommended_tone": "先共情、再回应行动、避免抢先定性",
        "analysis_summary": "食品安全高风险事件。",
    },
    "redteam_review": {
        "issues": ["缺少具体整改动作"],
        "attack_summary": "公众可能质疑行动不具体。",
        "suggestions": ["补充核查范围"],
    },
    "legal_review": {
        "legal_risks": ["避免提前定责"],
        "safe_points": ["使用核查和监管配合表达"],
        "revision_advice": ["使用条件式表达"],
        "public_opinion_suggestions": ["补充后续更新时间"],
        "integrated_revision_tasks": ["补充整改动作"],
        "legal_safety_score_hint": 8,
        "review_summary": "整体稳妥。",
    },
}
EXPECTED_FIELDS = {
    "final_statement",
    "scores",
    "recommendation",
    "reason",
    "decision_summary",
}


def test_decision_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert isinstance(result["final_statement"], str)
    assert isinstance(result["scores"], dict)
    assert isinstance(result["recommendation"], str)
    assert isinstance(result["reason"], str)
    assert isinstance(result["decision_summary"], str)
    assert set(result["scores"].keys()) == {"legal_safety", "empathy", "robustness"}
    assert all(isinstance(result["scores"][field], int) for field in result["scores"])


def test_decision_agent_llm_mode_success(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        decision_agent,
        "call_llm",
        lambda prompt: """
        {
          "final_statement": "我们已启动核查，并将持续说明进展。",
          "scores": {
            "legal_safety": 8,
            "empathy": 8,
            "robustness": 7
          },
          "recommendation": "publish",
          "reason": "当前版本适合作为对外回应底稿。"
        }
        """,
    )

    result = decision_agent.run(TEST_PAYLOAD)

    assert result == {
        "final_statement": "我们已启动核查，并将持续说明进展。",
        "scores": {
            "legal_safety": 8,
            "empathy": 8,
            "robustness": 7,
        },
        "recommendation": "publish",
        "reason": "当前版本适合作为对外回应底稿。",
        "decision_summary": "当前版本适合作为对外回应底稿。",
    }


def test_decision_agent_llm_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        decision_agent,
        "call_llm",
        lambda prompt: '{"final_statement": "missing scores"}',
    )

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert set(result["scores"].keys()) == {"legal_safety", "empathy", "robustness"}
