from backend.agents import decision_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "writer_v2": {
        "statement": "我们已关注相关情况，并将配合监管开展专项核查。",
    },
    "second_draft": "我们已关注相关情况，并将配合监管开展专项核查。",
    "sentiment_analysis": {"risk_level": "high"},
    "redteam_review": {
        "issues": ["缺少更新时间"],
        "suggestions": ["补充后续更新时间"],
    },
    "legal_review": {
        "legal_safety_score_hint": 8,
        "revision_advice": ["避免提前定责"],
        "integrated_revision_tasks": ["补充核查范围"],
    },
    "evaluation": {
        "legal_safety_score": 8,
        "empathy_score": 8,
        "robustness_score": 7,
        "passed": True,
    },
}
EXPECTED_FIELDS = {
    "final_statement",
    "scores",
    "recommendation",
    "reason",
    "decision_summary",
}


def test_decision_agent_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    get_config.cache_clear()

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert result["final_statement"] == TEST_PAYLOAD["second_draft"]


def test_decision_agent_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: "not json")

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert result["final_statement"] == TEST_PAYLOAD["second_draft"]


def test_decision_agent_llm_valid_json_is_parsed(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    def fake_call_llm(prompt):
        assert "企业危机响应首席决策官" in prompt
        assert "writer_v2" in prompt
        assert "legal_review" in prompt
        assert "redteam_review" in prompt
        assert "evaluation" in prompt
        return """
        {
          "final_statement": "我们已关注相关情况，并将配合监管开展专项核查。",
          "scores": {
            "legal_safety": 9,
            "empathy": 8,
            "robustness": 8
          },
          "recommendation": "publish",
          "reason": "声明法律风险可控，已吸收红队和法律建议。"
        }
        """

    monkeypatch.setattr(decision_agent, "call_llm", fake_call_llm)

    result = decision_agent.run(TEST_PAYLOAD)

    assert result == {
        "final_statement": "我们已关注相关情况，并将配合监管开展专项核查。",
        "scores": {
            "legal_safety": 9,
            "empathy": 8,
            "robustness": 8,
        },
        "recommendation": "publish",
        "reason": "声明法律风险可控，已吸收红队和法律建议。",
        "decision_summary": "声明法律风险可控，已吸收红队和法律建议。",
    }
