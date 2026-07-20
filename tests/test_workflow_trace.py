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
