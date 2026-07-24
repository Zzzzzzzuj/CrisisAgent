from backend.core.checkpoint import (
    delete_checkpoint,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from backend.core.human import request_review
from backend.core.state import WAITING_HUMAN, AgentState


def test_checkpoint_saves_and_loads_state(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-1", plan_id="plan-1", event="event")
    state.set_result("writer", {"statement": "draft"})

    save_checkpoint(state, checkpoint_path)
    restored = load_checkpoint("session-1", checkpoint_path)

    assert restored is not None
    assert restored.session_id == "session-1"
    assert restored.plan_id == "plan-1"
    assert restored.event == "event"
    assert restored.get_result("writer") == {"statement": "draft"}


def test_checkpoint_restores_waiting_human_status_and_approval(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-2", plan_id="plan-2", event="event")
    request_review(
        state,
        reason="High risk requires human review.",
        reviewer="alice",
        comment="Please review.",
    )

    save_checkpoint(state, checkpoint_path)
    restored = load_checkpoint("session-2", checkpoint_path)

    assert restored.status == WAITING_HUMAN
    assert restored.approval["required"] is True
    assert restored.approval["decision"] == "pending"
    assert restored.approval["reviewer"] == "alice"
    assert restored.approval["comment"] == "Please review."
    assert restored.approval["reason"] == "High risk requires human review."
    assert restored.approval["timestamp"]


def test_checkpoint_restores_trace_and_results(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-3", plan_id="plan-3", event="event")
    state.set_result("sentiment", {"risk_level": "high"})
    state.add_trace(
        {
            "agent": "sentiment",
            "reason": "analyze",
            "start_time": "start",
            "end_time": "end",
            "status": "success",
            "output": {"risk_level": "high"},
            "error": None,
        }
    )

    save_checkpoint(state, checkpoint_path)
    restored = load_checkpoint("session-3", checkpoint_path)

    assert restored.get_result("sentiment") == {"risk_level": "high"}
    assert restored.trace == [
        {
            "agent": "sentiment",
            "reason": "analyze",
            "start_time": "start",
            "end_time": "end",
            "status": "success",
            "output": {"risk_level": "high"},
            "error": None,
        }
    ]


def test_checkpoint_saves_multiple_sessions_independently(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    first = AgentState(session_id="session-a", plan_id="plan-a", event="event a")
    second = AgentState(session_id="session-b", plan_id="plan-b", event="event b")
    first.set_result("writer", {"statement": "a"})
    second.set_result("writer", {"statement": "b"})

    save_checkpoint(first, checkpoint_path)
    save_checkpoint(second, checkpoint_path)

    restored_first = load_checkpoint("session-a", checkpoint_path)
    restored_second = load_checkpoint("session-b", checkpoint_path)

    assert restored_first.get_result("writer") == {"statement": "a"}
    assert restored_second.get_result("writer") == {"statement": "b"}
    assert {item["session_id"] for item in list_checkpoints(checkpoint_path)} == {
        "session-a",
        "session-b",
    }


def test_checkpoint_missing_session_returns_none(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"

    assert load_checkpoint("missing", checkpoint_path) is None


def test_checkpoint_delete_session(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-4", plan_id="plan-4", event="event")
    save_checkpoint(state, checkpoint_path)

    assert delete_checkpoint("session-4", checkpoint_path) is True
    assert load_checkpoint("session-4", checkpoint_path) is None
    assert delete_checkpoint("session-4", checkpoint_path) is False


def test_agent_state_to_dict_and_from_dict_roundtrip():
    state = AgentState(
        session_id="session-5",
        plan_id="plan-5",
        event="event",
        metadata={"category": "food_safety"},
    )
    state.current_agent = "legal"
    state.mark_failed("legal", "failed")
    state.set_result("writer", {"statement": "draft"})

    restored = AgentState.from_dict(state.to_dict())

    assert restored.session_id == state.session_id
    assert restored.plan_id == state.plan_id
    assert restored.event == state.event
    assert restored.status == state.status
    assert restored.metadata == {"category": "food_safety"}
    assert restored.current_agent == "legal"
    assert restored.failed_agents == [{"agent": "legal", "reason": "failed"}]
    assert restored.get_result("writer") == {"statement": "draft"}
