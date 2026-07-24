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

    def fail_if_called(*args, **kwargs):
        raise AssertionError("memory retriever should not be called in mock mode")

    def context_fail_if_called(*args, **kwargs):
        raise AssertionError("ContextManager should not be used in mock mode")

    monkeypatch.setattr(writer_agent, "retrieve_memories", fail_if_called)
    monkeypatch.setattr(writer_agent, "ContextManager", context_fail_if_called)

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)

    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert all(isinstance(result[field], str) for field in result)
    assert result["tone"] == "先共情、再回应行动、避免抢先定性"
    assert writer_agent.get_last_memory_info()["enabled"] is False
    assert writer_agent.get_last_context_info() == {
        "before_tokens": 0,
        "after_tokens": 0,
        "sources": [],
    }


def test_writer_agent_llm_mode_uses_prompt_and_normalization(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {"memories": [], "context": ""},
    )
    monkeypatch.setattr(
        writer_agent,
        "call_llm",
        lambda prompt: """
        {
          "statement": "我们已注意到相关情况，并已启动核查。",
          "strategy": "先回应关切，再说明核查动作。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "基于输入事件生成第一版文案。"
        }
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

    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {"memories": [], "context": ""},
    )
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: '{"statement": "only one field"}')

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)

    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert result["tone"] == "先共情、再回应行动、避免抢先定性"


def test_writer_agent_llm_prompt_includes_memory_context(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {
            "memories": [{"memory_id": "memory-1", "category": "food_safety"}],
            "context": "historical strategy: 先共情，再说明核查和监管配合。",
        },
    )

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "statement": "我们已注意到相关情况，并启动核查。",
          "strategy": "参考历史经验，先共情再说明行动。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "已参考历史危机经验。"
        }
        """

    monkeypatch.setattr(writer_agent, "call_llm", fake_call_llm)

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)
    memory_info = writer_agent.get_last_memory_info()

    assert "historical strategy" in captured_prompt["value"]
    assert "[event]" in captured_prompt["value"]
    assert "[sentiment_analysis]" in captured_prompt["value"]
    assert "[memory_context]" in captured_prompt["value"]
    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert memory_info["enabled"] is True
    assert memory_info["hit"] is True
    assert memory_info["categories"] == ["food_safety"]
    assert memory_info["memory_ids"] == ["memory-1"]
    assert writer_agent.get_last_context_info()["sources"] == [
        "event",
        "sentiment_analysis",
        "memory_context",
    ]


def test_writer_agent_context_token_limit_is_applied(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(writer_agent, "CONTEXT_MAX_TOKENS", 17)
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {
            "memories": [{"memory_id": "memory-1", "category": "food_safety"}],
            "context": "historical strategy with many tokens should be dropped",
        },
    )

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "statement": "已根据有限上下文生成声明。",
          "strategy": "优先保留高优先级输入。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "context token limit applied"
        }
        """

    monkeypatch.setattr(writer_agent, "call_llm", fake_call_llm)

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)
    context_info = writer_agent.get_last_context_info()

    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert "[event]" in captured_prompt["value"]
    assert "[memory_context]" not in captured_prompt["value"]
    assert context_info["before_tokens"] > context_info["after_tokens"]
    assert "memory_context" not in context_info["sources"]


def test_writer_agent_memory_failure_continues_llm(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}

    def failing_memory(*args, **kwargs):
        raise RuntimeError("memory unavailable")

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "statement": "我们已注意到相关情况，并启动核查。",
          "strategy": "无历史经验时基于当前输入生成。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "memory unavailable"
        }
        """

    monkeypatch.setattr(writer_agent, "retrieve_memories", failing_memory)
    monkeypatch.setattr(writer_agent, "call_llm", fake_call_llm)

    result = writer_agent.generate_first_draft(TEST_PAYLOAD)
    memory_info = writer_agent.get_last_memory_info()
    context_info = writer_agent.get_last_context_info()

    assert "context:" in captured_prompt["value"]
    assert set(result.keys()) == {"statement", "strategy", "tone", "notes"}
    assert memory_info["enabled"] is True
    assert memory_info["hit"] is False
    assert context_info["sources"] == ["event", "sentiment_analysis"]
