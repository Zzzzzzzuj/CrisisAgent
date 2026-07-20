from backend.agents import redteam_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "draft": (
        "我们已关注到关于本次事件的网络反馈，对由此引发的公众担忧深表重视。"
        "公司已第一时间启动内部核查程序，对涉及批次、采购与生产环节展开全面排查。"
        "在事实进一步核实前，我们将及时同步调查进展，并积极配合相关监管要求。"
        "对于事件给消费者带来的不安，我们表示诚挚歉意。"
    ),
}


def test_redteam_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = redteam_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == {"issues", "attack_summary", "suggestions"}
    assert isinstance(result["issues"], list)
    assert all(isinstance(item, str) for item in result["issues"])
    assert isinstance(result["attack_summary"], str)
    assert isinstance(result["suggestions"], list)
    assert all(isinstance(item, str) for item in result["suggestions"])


def test_redteam_agent_llm_mode_uses_parser_and_normalization(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        redteam_agent,
        "call_llm",
        lambda prompt: """
        ```json
        {
          "issues": ["表态偏模板化", "整改动作不够具体"],
          "attack_summary": "媒体可能质疑企业回应力度不足。",
          "suggestions": ["增加行动承诺", "强化对消费者担忧的回应"]
        }
        ```
        """,
    )

    result = redteam_agent.run(TEST_PAYLOAD)

    assert result == {
        "issues": ["表态偏模板化", "整改动作不够具体"],
        "attack_summary": "媒体可能质疑企业回应力度不足。",
        "suggestions": ["增加行动承诺", "强化对消费者担忧的回应"],
    }


def test_redteam_agent_llm_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: '{"attack_summary": "only one field"}')

    result = redteam_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == {"issues", "attack_summary", "suggestions"}
    assert isinstance(result["issues"], list)
    assert isinstance(result["suggestions"], list)
