import pytest

from backend.core.executor import execute
from backend.core.state import COMPLETED, CREATED, QUEUED, RUNNING, WAITING_HUMAN, AgentState


def test_agent_state_crud():
    state = AgentState(
        session_id="session-1",
        plan_id="plan-1",
        event="test event",
        metadata={"category": "food_safety"},
    )

    state.set_result("sentiment", {"risk_level": "high"})

    assert state.get_result("sentiment") == {"risk_level": "high"}
    assert state.get_result("missing") is None
    assert state.get_all_results() == {"sentiment": {"risk_level": "high"}}
    assert state.to_context()["metadata"] == {"category": "food_safety"}


def test_agent_state_starts_created_and_allows_valid_transitions():
    state = AgentState(session_id="session-status", plan_id="plan", event="event")

    assert state.status == CREATED

    state.set_status(QUEUED)
    state.set_status(RUNNING)
    state.set_status(WAITING_HUMAN)
    state.set_status(RUNNING)
    state.set_status(COMPLETED)

    assert state.status == COMPLETED


def test_agent_state_rejects_invalid_transition_from_completed():
    state = AgentState(session_id="session-invalid", plan_id="plan", event="event")
    state.set_status(COMPLETED)

    with pytest.raises(ValueError):
        state.set_status(RUNNING)


def test_agents_can_share_state_results_through_executor():
    state = AgentState(session_id="session-1", plan_id="plan-2", event="test event")
    plan = {
        "plan_id": "plan-2",
        "plan": [
            {"agent": "sentiment", "reason": "analyze risk"},
            {"agent": "writer", "reason": "write response"},
        ],
    }

    def sentiment_runner(context):
        return {"risk_level": "high"}

    def writer_runner(payload):
        sentiment = payload["sentiment_analysis"]
        return {"statement": f"risk={sentiment['risk_level']}"}

    result = execute(
        plan,
        state,
        agent_registry={
            "sentiment": sentiment_runner,
            "writer": writer_runner,
        },
    )

    assert result["executed_agents"] == ["sentiment", "writer"]
    assert state.get_result("writer") == {"statement": "risk=high"}


def test_executor_successful_run_writes_results_to_state():
    state = AgentState(session_id="session-1", plan_id="plan-3", event="test event")
    plan = {
        "plan_id": "plan-3",
        "plan": [{"agent": "decision", "reason": "decide"}],
    }

    result = execute(
        plan,
        state,
        agent_registry={"decision": lambda context: {"final_statement": "ok"}},
    )

    assert state.current_agent is None
    assert state.get_result("decision") == {"final_statement": "ok"}
    assert result["results"] == {"decision": {"final_statement": "ok"}}
    assert state.trace[0]["status"] == "success"
    assert state.trace[0]["output"] == {"final_statement": "ok"}


def test_executor_agent_exception_keeps_state_results_intact():
    state = AgentState(session_id="session-1", plan_id="plan-4", event="test event")
    plan = {
        "plan_id": "plan-4",
        "plan": [
            {"agent": "sentiment", "reason": "success first"},
            {"agent": "legal", "reason": "fail second"},
            {"agent": "writer", "reason": "continue third"},
        ],
    }

    def failing_runner(context):
        raise RuntimeError("legal failed")

    result = execute(
        plan,
        state,
        agent_registry={
            "sentiment": lambda context: {"risk_level": "high"},
            "legal": failing_runner,
            "writer": lambda payload: {"seen": payload["sentiment_analysis"]["risk_level"]},
        },
    )

    assert state.current_agent is None
    assert state.get_result("sentiment") == {"risk_level": "high"}
    assert state.get_result("legal") is None
    assert state.get_result("writer") == {"seen": "high"}
    assert result["executed_agents"] == ["sentiment", "writer"]
    assert result["failed_agents"][0]["agent"] == "legal"
    assert "RuntimeError: legal failed" in result["failed_agents"][0]["reason"]


def test_execution_trace_records_success_and_failed_status():
    state = AgentState(session_id="session-1", plan_id="plan-5", event="test event")
    plan = {
        "plan_id": "plan-5",
        "plan": [
            {"agent": "sentiment", "reason": "ok"},
            {"agent": "unknown", "reason": "missing"},
        ],
    }

    result = execute(
        plan,
        state,
        agent_registry={"sentiment": lambda context: {"risk_level": "low"}},
    )

    assert [item["status"] for item in result["execution_trace"]] == ["success", "failed"]
    assert [item["status"] for item in state.trace] == ["success", "failed"]
    assert state.failed_agents == [
        {
            "agent": "unknown",
            "reason": "Agent is not registered.",
        }
    ]
