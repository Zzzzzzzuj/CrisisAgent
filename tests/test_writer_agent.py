from backend.agents import writer_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "sentiment_analysis": {
        "risk_level": "high",
        "public_emotion": "angry",
        "keywords": ["过期原料", "传播视频", "监管介入"],
        "recommended_tone": "先共情、再回应行动、避免抢先定性",
        "analysis_summary": "当前事件具有较强传播性和监管敏感性。",
    },
}


def test_writer_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)

    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert all(isinstance(result[field], str) for field in result)
    assert result["tone"] == "先共情、再回应行动、避免抢先定性"


def test_writer_agent_llm_mode_uses_prompt_and_normalization(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        writer_agent,
        "call_llm",
        lambda prompt: """
        ```json
        {
          "statement": "我们已注意到相关情况，并已启动核查。",
          "strategy": "先回应关切，再说明核查动作。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "基于输入事件生成第一版文案。"
        }
        ```
        """,
    )

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)

    assert result == {
        "statement": "我们已注意到相关情况，并已启动核查。",
        "strategy": "先回应关切，再说明核查动作。",
        "tone": "先共情、再回应行动、避免抢先定性",
        "notes": "基于输入事件生成第一版文案。",
    }


def test_writer_agent_llm_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: '{"statement": "only one field"}')

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)

    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert result["tone"] == "先共情、再回应行动、避免抢先定性"
