from backend.config import get_config
from backend.schemas import CrisisRunRequest
from backend.workflow import run_crisis_workflow


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
TRACE_FIELDS = {
    "agent",
    "name",
    "input",
    "output",
    "start_time",
    "end_time",
    "status",
    "mode",
    "fallback",
    "rag",
    "memory",
    "context",
    "tools",
}


def test_workflow_runs_and_trace_fields_are_complete_in_mock_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    assert sorted(response.keys()) == ["agent_trace", "final_statement", "scores", "session_id"]
    assert len(response["agent_trace"]) == 6

    for item in response["agent_trace"]:
        assert set(item.keys()) == TRACE_FIELDS
        assert isinstance(item["start_time"], str)
        assert isinstance(item["end_time"], str)
        assert item["status"] == "success"
        assert item["mode"] == "mock"
        assert item["fallback"] is False
        assert item["tools"] == []

    legal_trace = response["agent_trace"][3]
    assert legal_trace["agent"] == "Agent B"
    assert legal_trace["rag"]["enabled"] is False
    assert legal_trace["rag"]["hit"] is False
    assert legal_trace["rag"]["sources"] == []
    assert legal_trace["rag"]["count"] == 0

    first_writer_trace = response["agent_trace"][1]
    assert first_writer_trace["agent"] == "Agent C"
    assert first_writer_trace["memory"] is None
    assert first_writer_trace["context"] is None


def test_workflow_trace_records_agent_a_tool_success_in_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    import backend.agents.sentiment_agent as sentiment_agent
    import backend.agents.writer_agent as writer_agent
    import backend.agents.redteam_agent as redteam_agent
    import backend.agents.legal_agent as legal_agent
    import backend.agents.decision_agent as decision_agent

    class FakeTool:
        def run(self, params):
            return {
                "emotion": "angry",
                "heat_level": "high",
                "trend": "rising",
            }

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", lambda: FakeTool())
    monkeypatch.setattr(
        sentiment_agent,
        "call_llm",
        lambda prompt: """
        {
          "risk_level": "high",
          "public_emotion": "angry",
          "keywords": ["过期原料", "监管介入"],
          "recommended_tone": "先共情、再回应行动、避免抢先定性",
          "analysis_summary": "工具结果和事件文本均显示高风险。"
        }
        """,
    )
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    agent_a_trace = response["agent_trace"][0]
    assert agent_a_trace["agent"] == "Agent A"
    assert len(agent_a_trace["tools"]) == 1
    tool_trace = agent_a_trace["tools"][0]
    assert tool_trace["name"] == "sentiment_analysis"
    assert tool_trace["input"] == {"event": TEST_EVENT}
    assert tool_trace["output"] == {
        "emotion": "angry",
        "heat_level": "high",
        "trend": "rising",
    }
    assert tool_trace["success"] is True
    assert tool_trace["duration_ms"] >= 0


def test_workflow_trace_records_agent_a_tool_failure_in_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    import backend.agents.sentiment_agent as sentiment_agent
    import backend.agents.writer_agent as writer_agent
    import backend.agents.redteam_agent as redteam_agent
    import backend.agents.legal_agent as legal_agent
    import backend.agents.decision_agent as decision_agent

    class FailingTool:
        def run(self, params):
            raise RuntimeError("tool unavailable")

    monkeypatch.setattr(sentiment_agent, "_get_sentiment_tool", lambda: FailingTool())
    monkeypatch.setattr(
        sentiment_agent,
        "call_llm",
        lambda prompt: """
        {
          "risk_level": "high",
          "public_emotion": "angry",
          "keywords": ["过期原料"],
          "recommended_tone": "先共情、再回应行动、避免抢先定性",
          "analysis_summary": "工具失败时仍基于事件文本完成分析。"
        }
        """,
    )
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    agent_a_trace = response["agent_trace"][0]
    tool_trace = agent_a_trace["tools"][0]
    assert tool_trace["name"] == "sentiment_analysis"
    assert tool_trace["input"] == {"event": TEST_EVENT}
    assert tool_trace["output"] is None
    assert tool_trace["success"] is False
    assert tool_trace["duration_ms"] >= 0


def test_workflow_trace_records_agent_c_context_info_in_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    import backend.agents.sentiment_agent as sentiment_agent
    import backend.agents.writer_agent as writer_agent
    import backend.agents.redteam_agent as redteam_agent
    import backend.agents.legal_agent as legal_agent
    import backend.agents.decision_agent as decision_agent

    monkeypatch.setattr(
        sentiment_agent,
        "call_llm",
        lambda prompt: """
        {
          "risk_level": "high",
          "public_emotion": "angry",
          "keywords": ["过期原料"],
          "recommended_tone": "先共情、再回应行动、避免抢先定性",
          "analysis_summary": "高风险事件。"
        }
        """,
    )
    monkeypatch.setattr(
        writer_agent,
        "retrieve_memories",
        lambda query, top_k=3: {
            "memories": [{"memory_id": "memory-1", "category": "food_safety"}],
            "context": "historical strategy: 先共情，再说明核查和监管配合。",
        },
    )
    monkeypatch.setattr(
        writer_agent,
        "call_llm",
        lambda prompt: """
        {
          "statement": "我们已注意到相关情况，并启动核查。",
          "strategy": "基于上下文生成第一版声明。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "notes": "context injected"
        }
        """,
    )
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    writer_trace = response["agent_trace"][1]
    assert writer_trace["agent"] == "Agent C"
    assert writer_trace["context"]["before_tokens"] >= writer_trace["context"]["after_tokens"]
    assert writer_trace["context"]["after_tokens"] > 0
    assert writer_trace["context"]["sources"] == [
        "event",
        "sentiment_analysis",
        "memory_context",
    ]


def test_workflow_trace_marks_fallback_in_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    import backend.agents.sentiment_agent as sentiment_agent
    import backend.agents.writer_agent as writer_agent
    import backend.agents.redteam_agent as redteam_agent
    import backend.agents.legal_agent as legal_agent
    import backend.agents.decision_agent as decision_agent

    monkeypatch.setattr(sentiment_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    assert len(response["agent_trace"]) == 6
    fallback_agents = [item for item in response["agent_trace"] if item["fallback"]]
    assert [item["agent"] for item in fallback_agents] == [
        "Agent A",
        "Agent C",
        "Agent D",
        "Agent B",
        "Agent E",
    ]

    second_draft_trace = response["agent_trace"][4]
    assert second_draft_trace["agent"] == "Agent C"
    assert second_draft_trace["mode"] == "mock"
    assert second_draft_trace["fallback"] is False
    assert second_draft_trace["status"] == "success"


def test_workflow_trace_records_agent_b_rag_info_in_llm_mode(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    import backend.agents.sentiment_agent as sentiment_agent
    import backend.agents.writer_agent as writer_agent
    import backend.agents.redteam_agent as redteam_agent
    import backend.agents.legal_agent as legal_agent
    import backend.agents.decision_agent as decision_agent

    monkeypatch.setattr(sentiment_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(redteam_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))
    monkeypatch.setattr(decision_agent, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("llm down")))

    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[food_safety.md]\n食品安全危机回应需要说明核查和监管配合。",
            "sources": [
                {"source": "food_safety.md", "title": "食品安全", "score": 1.0},
                {"source": "legal_risk_rules.md", "title": "法律风险", "score": 0.8},
            ],
        },
    )
    monkeypatch.setattr(
        legal_agent,
        "call_llm",
        lambda prompt: """
        {
          "legal_risks": ["避免提前定责。"],
          "safe_points": ["保留监管配合表达。"],
          "revision_advice": ["使用条件式责任表达。"],
          "public_opinion_suggestions": ["回应消费者担忧。"],
          "integrated_revision_tasks": ["补充核查范围。"],
          "legal_safety_score_hint": 8,
          "review_summary": "已参考RAG知识。"
        }
        """,
    )

    response = run_crisis_workflow(CrisisRunRequest(event=TEST_EVENT)).model_dump()

    legal_trace = response["agent_trace"][3]
    assert legal_trace["agent"] == "Agent B"
    assert legal_trace["rag"]["enabled"] is True
    assert legal_trace["rag"]["hit"] is True
    assert legal_trace["rag"]["sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert legal_trace["rag"]["count"] == 2
    assert "query" in legal_trace["rag"]
    assert "chunks" in legal_trace["rag"]
    assert "scores" in legal_trace["rag"]
    assert "rerank_scores" in legal_trace["rag"]
