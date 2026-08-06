from backend.agents import redteam_agent


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "draft": (
        "我们已关注到相关情况，并已启动核查。"
        "后续将根据进展持续同步。"
    ),
}
EXPECTED_SCHEMA = {"issues", "attack_summary", "suggestions"}


def test_redteam_agent_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    result = redteam_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert isinstance(result["issues"], list)
    assert isinstance(result["attack_summary"], str)
    assert isinstance(result["suggestions"], list)


def test_redteam_agent_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: "not json")

    result = redteam_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_SCHEMA
    assert isinstance(result["issues"], list)
    assert isinstance(result["suggestions"], list)


def test_redteam_agent_llm_valid_json_is_parsed(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def fake_call_llm(prompt):
        assert "红队攻击 Agent D" in prompt
        assert "公众质疑者" in prompt
        assert TEST_PAYLOAD["event"] in prompt
        assert TEST_PAYLOAD["draft"] in prompt
        return """
        {
          "issues": ["声明较模板化", "缺少具体整改动作"],
          "attack_summary": "公众可能质疑企业只是程序化回应，没有给出明确行动。",
          "suggestions": ["补充核查范围", "说明后续整改和更新时间"]
        }
        """

    monkeypatch.setattr(redteam_agent, "call_llm", fake_call_llm)

    result = redteam_agent.run(TEST_PAYLOAD)

    assert result == {
        "issues": ["声明较模板化", "缺少具体整改动作"],
        "attack_summary": "公众可能质疑企业只是程序化回应，没有给出明确行动。",
        "suggestions": ["补充核查范围", "说明后续整改和更新时间"],
    }
