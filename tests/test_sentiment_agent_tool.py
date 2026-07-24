import pytest

from backend.agents import sentiment_agent
from backend.config import get_config


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
EXPECTED_SCHEMA = {
    "risk_level",
    "public_emotion",
    "keywords",
    "recommended_tone",
    "analysis_summary",
}


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def enable_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()


def test_sentiment_agent_llm_mode_calls_sentiment_tool(monkeypatch):
    enable_llm_mode(monkeypatch)
    captured = {}

    class FakeTool:
        def run(self, params):
            captured["tool_input"] = params
            return {
                "emotion": "angry",
                "heat_level": "high",
                "trend": "rising",
            }

    def fake_call_llm(prompt):
        captured["prompt"] = prompt
        return """
        {
          "risk_level": "high",
          "public_emotion": "angry",
          "keywords": ["过期原料", "监管介入"],
          "recommended_tone": "先共情、再回应行动、避免抢先定性",
          "analysis_summary": "事件引发明显愤怒情绪，需要及时回应。"
        }
        """

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", lambda: FakeTool())
    monkeypatch.setattr(sentiment_agent, "call_llm", fake_call_llm)

    result = sentiment_agent.run(TEST_EVENT)
    tool_info = sentiment_agent.get_last_tool_info()

    assert captured["tool_input"] == {"event": TEST_EVENT}
    assert "tool_result:" in captured["prompt"]
    assert "heat_level" in captured["prompt"]
    assert set(result.keys()) == EXPECTED_SCHEMA
    assert tool_info["name"] == "sentiment_analysis"
    assert tool_info["input"] == {"event": TEST_EVENT}
    assert tool_info["output"] == {
        "emotion": "angry",
        "heat_level": "high",
        "trend": "rising",
    }
    assert tool_info["success"] is True
    assert tool_info["duration_ms"] >= 0


def test_sentiment_agent_tool_failure_continues_without_tool_result(monkeypatch):
    enable_llm_mode(monkeypatch)
    captured = {}

    class FailingTool:
        def run(self, params):
            raise RuntimeError("tool unavailable")

    def fake_call_llm(prompt):
        captured["prompt"] = prompt
        return """
        {
          "risk_level": "high",
          "public_emotion": "anger and distrust",
          "keywords": ["过期原料"],
          "recommended_tone": "Respond with empathy first, then action, and avoid premature judgment.",
          "analysis_summary": "工具不可用时仍基于事件文本完成分析。"
        }
        """

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", lambda: FailingTool())
    monkeypatch.setattr(sentiment_agent, "call_llm", fake_call_llm)

    result = sentiment_agent.run(TEST_EVENT)
    tool_info = sentiment_agent.get_last_tool_info()

    assert "tool_result: {}" in captured["prompt"]
    assert set(result.keys()) == EXPECTED_SCHEMA
    assert result["public_emotion"] == "angry"
    assert tool_info["name"] == "sentiment_analysis"
    assert tool_info["input"] == {"event": TEST_EVENT}
    assert tool_info["output"] is None
    assert tool_info["success"] is False
    assert tool_info["duration_ms"] >= 0


def test_sentiment_agent_mock_mode_does_not_call_tool(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    def fail_if_called():
        raise AssertionError("sentiment tool should not be called in mock mode")

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", fail_if_called)

    result = sentiment_agent.run(TEST_EVENT)
    tool_info = sentiment_agent.get_last_tool_info()

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert tool_info == {
        "name": None,
        "input": None,
        "output": None,
        "success": False,
        "duration_ms": 0.0,
    }


def test_sentiment_agent_tool_path_keeps_output_schema(monkeypatch):
    enable_llm_mode(monkeypatch)

    class FakeTool:
        def run(self, params):
            return {
                "emotion": "worried",
                "heat_level": "medium",
                "trend": "stable",
            }

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", lambda: FakeTool())
    monkeypatch.setattr(
        sentiment_agent,
        "call_llm",
        lambda prompt: """
        {
          "risk_level": "medium",
          "public_emotion": "worried",
          "keywords": ["投诉"],
          "recommended_tone": "保持冷静、基于事实回应、避免情绪化对抗",
          "analysis_summary": "公众处于担忧状态，需要事实说明。"
        }
        """,
    )

    result = sentiment_agent.run(TEST_EVENT)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert isinstance(result["risk_level"], str)
    assert isinstance(result["public_emotion"], str)
    assert isinstance(result["keywords"], list)
    assert isinstance(result["recommended_tone"], str)
    assert isinstance(result["analysis_summary"], str)
