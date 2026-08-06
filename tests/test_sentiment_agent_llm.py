from backend.agents import sentiment_agent


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
EXPECTED_SCHEMA = {
    "risk_level",
    "public_emotion",
    "keywords",
    "recommended_tone",
    "analysis_summary",
}


def test_sentiment_agent_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    result = sentiment_agent.run(TEST_EVENT)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert result["public_emotion"] in {"angry", "worried", "neutral", "positive"}
    assert isinstance(result["keywords"], list)


def test_sentiment_agent_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(sentiment_agent, "call_llm", lambda prompt: "not valid json")

    result = sentiment_agent.run(TEST_EVENT)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert result["public_emotion"] in {"angry", "worried", "neutral", "positive"}
    assert isinstance(result["analysis_summary"], str)
