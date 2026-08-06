from backend.agents import writer_agent


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "sentiment_analysis": {
        "risk_level": "high",
        "public_emotion": "angry",
        "keywords": ["过期原料", "监管介入"],
        "recommended_tone": "先共情、再回应行动、避免抢先定性",
        "analysis_summary": "食品安全高风险事件。",
    },
}
EXPECTED_SCHEMA = {"statement", "strategy", "tone", "notes"}


def test_writer_agent_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {"memories": [], "context": ""},
    )

    result = writer_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert all(isinstance(result[field], str) for field in EXPECTED_SCHEMA)


def test_writer_agent_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {"memories": [], "context": ""},
    )
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: "not json")

    result = writer_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert all(isinstance(result[field], str) for field in EXPECTED_SCHEMA)


def test_writer_agent_llm_valid_json_is_parsed(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {"memories": [], "context": ""},
    )

    def fake_call_llm(prompt):
        assert "策略文案 Agent C" in prompt
        assert "sentiment_analysis" in prompt
        assert TEST_PAYLOAD["event"] in prompt
        return """
        {
          "statement": "我们已关注到相关情况，并已启动核查。",
          "strategy": "先回应公众关切，再说明核查行动。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "第一版声明。"
        }
        """

    monkeypatch.setattr(writer_agent, "call_llm", fake_call_llm)

    result = writer_agent.run(TEST_PAYLOAD)

    assert result == {
        "statement": "我们已关注到相关情况，并已启动核查。",
        "strategy": "先回应公众关切，再说明核查行动。",
        "tone": "先共情、再回应行动、避免抢先定性",
        "notes": "第一版声明。",
    }
