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

    legal_trace = response["agent_trace"][3]
    assert legal_trace["agent"] == "Agent B"
    assert legal_trace["rag"] == {
        "enabled": False,
        "hit": False,
        "sources": [],
        "count": 0,
    }


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
    assert legal_trace["rag"] == {
        "enabled": True,
        "hit": True,
        "sources": ["food_safety.md", "legal_risk_rules.md"],
        "count": 2,
    }
