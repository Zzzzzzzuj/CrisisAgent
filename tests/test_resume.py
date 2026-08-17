from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.human import approve, reject, request_review
from backend.core.resume import resume_agent_loop
from backend.core.state import COMPLETED, REJECTED, WAITING_HUMAN, AgentState


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播。"


def _plan(plan_id="resume-plan"):
    return {
        "plan_id": plan_id,
        "plan": [
            {"agent": "writer", "reason": "write"},
            {"agent": "decision", "reason": "decide"},
        ],
    }


def test_waiting_human_checkpoint_returns_waiting_without_approval(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-waiting", plan_id="plan-1", event=TEST_EVENT)
    request_review(state, reason="High risk requires review.")
    save_checkpoint(state, checkpoint_path)
    calls = {"planner": 0}

    def planner(payload):
        calls["planner"] += 1
        return _plan()

    result = resume_agent_loop(
        "session-waiting",
        checkpoint_path=checkpoint_path,
        planner=planner,
    )

    assert result["status"] == "waiting_human"
    assert result["stopped_reason"] == "human_approval_required"
    assert result["state_status"] == WAITING_HUMAN
    assert result["approval"]["decision"] == "pending"
    assert calls["planner"] == 0


def test_approved_checkpoint_continues_agent_loop(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(
        session_id="session-approved",
        plan_id="old-plan",
        event=TEST_EVENT,
        metadata={"planner_input": {"event": TEST_EVENT, "category": "food_safety", "risk_level": "high"}},
    )
    state.set_result("sentiment", {"risk_level": "high"})
    request_review(state, reason="High risk requires review.")
    approve(state, reviewer="alice", comment="Approved to continue.")
    save_checkpoint(state, checkpoint_path)
    calls = {"planner": 0, "executor": 0}

    def planner(payload):
        calls["planner"] += 1
        return _plan()

    def executor(plan, restored_state, agent_registry=None):
        calls["executor"] += 1
        restored_state.set_result("writer", {"statement": "draft"})
        restored_state.set_result("decision", {"final_statement": "ok"})
        restored_state.add_trace(
            {
                "agent": "decision",
                "reason": "decide",
                "start_time": "start",
                "end_time": "end",
                "status": "success",
                "output": {"final_statement": "ok"},
                "error": None,
            }
        )
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["writer", "decision"],
            "results": restored_state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(restored_state.trace),
        }

    result = resume_agent_loop(
        "session-approved",
        checkpoint_path=checkpoint_path,
        planner=planner,
        validator=lambda plan: plan,
        executor=executor,
        evaluator=lambda restored_state: {"passed": True, "issues": []},
    )

    assert result["status"] == "completed"
    assert result["session_id"] == "session-approved"
    assert result["plan_id"] == "resume-plan"
    assert result["results"]["sentiment"] == {"risk_level": "high"}
    assert result["results"]["decision"] == {"final_statement": "ok"}
    assert result["approval"]["decision"] == "approved"
    assert calls == {"planner": 1, "executor": 1}


def test_waiting_human_with_approved_decision_can_resume(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-approved-waiting", plan_id="plan-1", event=TEST_EVENT)
    request_review(state, reason="Review required.")
    state.approval["decision"] = "approved"
    save_checkpoint(state, checkpoint_path)

    def executor(plan, restored_state, agent_registry=None):
        restored_state.set_result("decision", {"final_statement": "ok"})
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["decision"],
            "results": restored_state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(restored_state.trace),
        }

    result = resume_agent_loop(
        "session-approved-waiting",
        checkpoint_path=checkpoint_path,
        planner=lambda payload: _plan(),
        validator=lambda plan: plan,
        executor=executor,
        evaluator=lambda restored_state: {"passed": True, "issues": []},
    )

    assert result["status"] == "completed"
    assert result["results"]["decision"] == {"final_statement": "ok"}


def test_rejected_checkpoint_does_not_continue(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-rejected", plan_id="plan-1", event=TEST_EVENT)
    request_review(state, reason="High risk requires review.")
    reject(state, reviewer="bob", comment="Reject response.")
    save_checkpoint(state, checkpoint_path)
    calls = {"planner": 0}

    def planner(payload):
        calls["planner"] += 1
        return _plan()

    result = resume_agent_loop(
        "session-rejected",
        checkpoint_path=checkpoint_path,
        planner=planner,
    )

    assert result["status"] == "failed"
    assert result["state_status"] == REJECTED
    assert result["stopped_reason"] == "human_rejected"
    assert result["approval"]["decision"] == "rejected"
    assert calls["planner"] == 0


def test_missing_checkpoint_returns_error(tmp_path):
    result = resume_agent_loop("missing-session", checkpoint_path=tmp_path / "checkpoints.json")

    assert result["status"] == "error"
    assert result["stopped_reason"] == "checkpoint_not_found"
    assert result["state"] is None
    assert "missing-session" in result["error"]


def test_resume_preserves_existing_trace_results_and_identity(tmp_path):
    checkpoint_path = tmp_path / "checkpoints.json"
    state = AgentState(session_id="session-preserve", plan_id="old-plan", event=TEST_EVENT)
    state.set_result("writer", {"statement": "old draft"})
    state.add_trace(
        {
            "agent": "writer",
            "reason": "old write",
            "start_time": "old-start",
            "end_time": "old-end",
            "status": "success",
            "output": {"statement": "old draft"},
            "error": None,
        }
    )
    request_review(state, reason="Need review.")
    approve(state, reviewer="alice", comment="Looks safe.")
    save_checkpoint(state, checkpoint_path)

    def executor(plan, restored_state, agent_registry=None):
        restored_state.set_result("decision", {"final_statement": "new final"})
        return {
            "plan_id": plan["plan_id"],
            "executed_agents": ["decision"],
            "results": restored_state.get_all_results(),
            "failed_agents": [],
            "execution_trace": list(restored_state.trace),
        }

    result = resume_agent_loop(
        "session-preserve",
        checkpoint_path=checkpoint_path,
        planner=lambda payload: _plan("new-plan"),
        validator=lambda plan: plan,
        executor=executor,
        evaluator=lambda restored_state: {"passed": True, "issues": []},
    )
    restored_checkpoint = load_checkpoint("session-preserve", checkpoint_path)

    assert result["session_id"] == "session-preserve"
    assert result["event"] == TEST_EVENT
    assert result["results"]["writer"] == {"statement": "old draft"}
    assert result["results"]["decision"] == {"final_statement": "new final"}
    assert result["execution_trace"][0]["agent"] == "writer"
    assert result["approval"]["reviewer"] == "alice"
    assert restored_checkpoint.session_id == "session-preserve"
    assert restored_checkpoint.plan_id == "new-plan"
    assert restored_checkpoint.status == COMPLETED
