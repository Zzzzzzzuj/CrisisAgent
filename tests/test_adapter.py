from backend.core.adapter import build_agent_input
from backend.core.executor import execute
from backend.core.state import AgentState


def test_adapter_builds_sentiment_input_schema():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")

    payload = build_agent_input("sentiment", state)

    assert payload == {"event": "test event"}


def test_adapter_builds_writer_input_schema_with_memory_context():
    state = AgentState(
        session_id="session-1",
        plan_id="plan-1",
        event="test event",
        metadata={"memory_context": "historical lesson"},
    )
    state.set_result("sentiment", {"risk_level": "high"})

    payload = build_agent_input("writer", state)

    assert payload == {
        "event": "test event",
        "sentiment_analysis": {"risk_level": "high"},
        "memory_context": "historical lesson",
    }


def test_adapter_builds_redteam_input_schema_from_writer_result():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")
    state.set_result("writer", {"statement": "draft statement"})

    payload = build_agent_input("redteam", state)

    assert payload == {
        "event": "test event",
        "draft": "draft statement",
    }


def test_adapter_builds_legal_input_schema_from_writer_and_redteam_results():
    state = AgentState(
        session_id="session-1",
        plan_id="plan-1",
        event="test event",
        metadata={"planner_input": {"category": "food_safety"}},
    )
    state.set_result("sentiment", {"risk_level": "high"})
    state.set_result("writer", {"statement": "draft statement"})
    state.set_result("redteam", {"issues": ["issue"], "suggestions": ["fix"]})

    payload = build_agent_input("legal", state)

    assert payload == {
        "event": "test event",
        "draft": "draft statement",
        "redteam_review": {"issues": ["issue"], "suggestions": ["fix"]},
        "sentiment_analysis": {"risk_level": "high"},
        "planner_input": {"category": "food_safety"},
        "category": "food_safety",
    }


def test_adapter_builds_decision_input_schema_with_all_results():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")
    state.set_result("sentiment", {"risk_level": "high"})
    state.set_result("writer", {"statement": "draft"})
    state.set_result("redteam", {"issues": ["issue"]})
    state.set_result("legal", {"legal_risks": []})
    state.set_result("writer_v2", {"statement": "second draft"})

    payload = build_agent_input("decision", state)

    assert payload == {
        "event": "test event",
        "second_draft": "second draft",
        "sentiment_analysis": {"risk_level": "high"},
        "redteam_review": {"issues": ["issue"]},
        "legal_review": {"legal_risks": []},
        "results": {
            "sentiment": {"risk_level": "high"},
            "writer": {"statement": "draft"},
            "redteam": {"issues": ["issue"]},
            "legal": {"legal_risks": []},
            "writer_v2": {"statement": "second draft"},
        },
    }


def test_adapter_builds_writer_v2_input_schema_from_reviews():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")
    state.set_result("writer", {"statement": "first draft"})
    state.set_result("redteam", {"issues": ["issue"]})
    state.set_result("legal", {"integrated_revision_tasks": ["revise"]})

    payload = build_agent_input("writer_v2", state)

    assert payload == {
        "event": "test event",
        "first_draft": {"statement": "first draft"},
        "redteam_review": {"issues": ["issue"]},
        "legal_review": {"integrated_revision_tasks": ["revise"]},
    }


def test_state_results_are_passed_to_later_agent_inputs():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")
    state.set_result("sentiment", {"risk_level": "high"})
    writer_payload = build_agent_input("writer", state)
    state.set_result("writer", {"statement": "draft statement"})
    redteam_payload = build_agent_input("redteam", state)

    assert writer_payload["sentiment_analysis"] == {"risk_level": "high"}
    assert redteam_payload["draft"] == "draft statement"


def test_executor_executes_through_adapter_successfully():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="test event")
    plan = {
        "plan_id": "plan-1",
        "plan": [
            {"agent": "writer", "reason": "write"},
            {"agent": "redteam", "reason": "review"},
            {"agent": "legal", "reason": "legal"},
            {"agent": "writer_v2", "reason": "rewrite"},
            {"agent": "decision", "reason": "decide"},
        ],
    }

    def writer(payload):
        assert payload == {
            "event": "test event",
            "sentiment_analysis": {},
        }
        return {"statement": "draft statement"}

    def redteam(payload):
        assert payload["draft"] == "draft statement"
        return {"issues": ["issue"], "suggestions": ["fix"]}

    def legal(payload):
        assert payload["draft"] == "draft statement"
        assert payload["redteam_review"] == {"issues": ["issue"], "suggestions": ["fix"]}
        return {"legal_risks": []}

    def writer_v2(payload):
        assert payload["first_draft"] == {"statement": "draft statement"}
        assert payload["redteam_review"] == {"issues": ["issue"], "suggestions": ["fix"]}
        assert payload["legal_review"] == {"legal_risks": []}
        return {"statement": "second draft"}

    def decision(payload):
        assert payload["second_draft"] == "second draft"
        assert payload["results"]["writer"] == {"statement": "draft statement"}
        assert payload["results"]["writer_v2"] == {"statement": "second draft"}
        assert payload["results"]["redteam"] == {"issues": ["issue"], "suggestions": ["fix"]}
        assert payload["results"]["legal"] == {"legal_risks": []}
        return {"final_statement": "ok"}

    result = execute(
        plan,
        state,
        agent_registry={
            "writer": writer,
            "redteam": redteam,
            "legal": legal,
            "writer_v2": writer_v2,
            "decision": decision,
        },
    )

    assert result["executed_agents"] == ["writer", "redteam", "legal", "writer_v2", "decision"]
    assert result["failed_agents"] == []
    assert state.get_result("decision") == {"final_statement": "ok"}
