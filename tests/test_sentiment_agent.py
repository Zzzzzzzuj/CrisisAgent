import os

from backend.agents import sentiment_agent
from backend.config import get_config


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def test_sentiment_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = sentiment_agent.run(TEST_EVENT)

    assert set(result.keys()) == {
        "risk_level",
        "public_emotion",
        "keywords",
        "recommended_tone",
        "analysis_summary",
    }
    assert isinstance(result["risk_level"], str)
    assert isinstance(result["public_emotion"], str)
    assert isinstance(result["keywords"], list)
    assert all(isinstance(item, str) for item in result["keywords"])
    assert isinstance(result["recommended_tone"], str)
    assert isinstance(result["analysis_summary"], str)

    assert result["public_emotion"] in {"angry", "worried", "neutral", "positive"}
    assert result["recommended_tone"] == "先共情、再回应行动、避免抢先定性"


def test_sentiment_agent_normalize_output_maps_emotion_and_tone():
    normalized = sentiment_agent._normalize_output(
        {
            "risk_level": "high",
            "public_emotion": "anger and distrust",
            "keywords": ["过期原料", "监管介入"],
            "recommended_tone": "Respond with empathy first, then action, and avoid premature judgment.",
            "analysis_summary": "该事件已引发明显舆情风险。",
        }
    )

    assert normalized["public_emotion"] == "angry"
    assert normalized["recommended_tone"] == "先共情、再回应行动、避免抢先定性"


def teardown_module():
    os.environ.pop("AGENT_MODE", None)
    get_config.cache_clear()
