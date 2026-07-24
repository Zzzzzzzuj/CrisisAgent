from backend.tools.sentiment_tool import SentimentAnalysisTool


def test_sentiment_tool_can_execute():
    tool = SentimentAnalysisTool()

    result = tool.run({"event": "某食品品牌被曝使用过期原料，监管介入，舆论持续发酵。"})

    assert result == {
        "emotion": "angry",
        "heat_level": "high",
        "trend": "rising",
    }


def test_sentiment_tool_output_structure_is_correct():
    tool = SentimentAnalysisTool()

    result = tool.run({"event": "用户投诉服务无法使用。"})

    assert set(result.keys()) == {"emotion", "heat_level", "trend"}
    assert isinstance(result["emotion"], str)
    assert isinstance(result["heat_level"], str)
    assert isinstance(result["trend"], str)


def test_sentiment_tool_rejects_invalid_params():
    tool = SentimentAnalysisTool()

    try:
        tool.run({"event": ""})
    except ValueError as exc:
        assert "event" in str(exc)
    else:
        raise AssertionError("Expected invalid event to fail.")
