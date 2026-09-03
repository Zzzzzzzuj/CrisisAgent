from backend.core.agent_loop import run_agent_loop
from backend.core.human import approve, reject, request_review
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, REJECTED, RUNNING, WAITING_HUMAN, AgentState


def test_high_risk_enters_waiting_human():
    result = run_agent_loop(
        "high risk event",
        planner=lambda payload: {
            "plan_id": "plan-1",
            "plan": [{"agent": "decision", "reason": "decide"}],
        },
        validator=lambda plan: plan,
        executor=lambda plan, state, agent_registry=None: _successful_execution(state, risk_level="high"),
    )

    assert result["status"] == "waiting_human"
    assert result["state_status"] == WAITING_HUMAN
    assert result["state"]["status"] == WAITING_HUMAN
    assert result["state"]["approval"]["decision"] == "pending"
    assert result["state"]["results"]["sentiment"]["risk_level"] == "high"
    assert result["approval"]["required"] is True
    assert result["approval"]["decision"] == "pending"
    assert "high_risk" in result["iterations"][0]["policy"]["triggers"]


def test_low_risk_auto_completes():
    result = run_agent_loop(
        "low risk event",
        planner=lambda payload: {
            "plan_id": "plan-2",
            "plan": [{"agent": "decision", "reason": "decide"}],
        },
        validator=lambda plan: plan,
        executor=lambda plan, state, agent_registry=None: _successful_execution(state, risk_level="low"),
    )

    assert result["status"] == "completed"
    assert result["state_status"] == COMPLETED
    assert result["state"]["status"] == COMPLETED
    assert result["state"]["approval"]["required"] is False
    assert result["approval"]["required"] is False


def test_approve_restores_running_status_and_records_reviewer_comment_timestamp():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="event")
    request_review(state, "High risk requires review.")

    trace = approve(state, reviewer="alice", comment="Looks safe.")

    assert state.status == RUNNING
    assert state.approval["decision"] == "approved"
    assert state.approval["reviewer"] == "alice"
    assert state.approval["comment"] == "Looks safe."
    assert state.approval["timestamp"]
    assert trace["status"] == "approved"


def test_reject_sets_failed_status_and_records_reviewer_comment_timestamp():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="event")
    request_review(state, "Low score requires review.")

    trace = reject(state, reviewer="bob", comment="Not acceptable.")

    assert state.status == REJECTED
    assert state.approval["decision"] == "rejected"
    assert state.approval["reviewer"] == "bob"
    assert state.approval["comment"] == "Not acceptable."
    assert state.approval["timestamp"]
    assert trace["status"] == "rejected"


def test_human_trace_is_complete():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="event")

    request_review(state, "Need review.", reviewer="alice", comment="Please check.")
    approve(state, reviewer="alice", comment="Approved.")

    human_traces = [item for item in state.trace if item["agent"] == "human_gate"]
    assert [item["status"] for item in human_traces] == ["waiting_human", "approved"]
    for item in human_traces:
        assert item["start_time"]
        assert item["end_time"]
        assert item["error"] is None
        assert "approval" in item["output"]
        assert "timestamp" in item["output"]["approval"]
        assert "reviewer" in item["output"]["approval"]
        assert "comment" in item["output"]["approval"]
        assert "decision" in item["output"]["approval"]


def test_policy_uses_quality_failure_for_human_review():
    state = AgentState(session_id="session-1", plan_id="plan-1", event="event")
    state.set_result(
        "decision",
        {
            "final_statement": "ok",
            "scores": {
                "legal_safety": 5,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )

    evaluation = evaluate_runtime_state(state)
    policy = evaluate_human_policy(state, evaluation)

    assert evaluation["passed"] is False
    assert policy["required"] is True
    assert "quality_failed" in policy["triggers"]
    assert "low_legal_safety" in policy["triggers"]


def test_policy_uses_rag_evidence_low_confidence_for_human_review():
    state = AgentState(session_id="session-rag-low", plan_id="plan-1", event="event")
    state.set_result("sentiment", {"risk_level": "low"})
    state.set_result(
        "decision",
        {
            "final_statement": "ok",
            "scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )
    state.add_trace(
        {
            "agent": "legal",
            "status": "success",
            "rag": {
                "evidence_quality": {
                    "evaluated": True,
                    "quality": "low",
                    "low_confidence": True,
                    "should_trigger_human_review": True,
                    "reasons": ["high_context_pollution"],
                }
            },
        }
    )

    policy = evaluate_human_policy(state, {"passed": True, "issues": []})

    assert policy["required"] is True
    assert "rag_evidence_low_confidence" in policy["triggers"]
    assert "rag_evidence_low_confidence" in policy["reason"]


def test_policy_ignores_not_applicable_rag_evidence_quality():
    state = AgentState(session_id="session-rag-skip", plan_id="plan-1", event="event")
    state.set_result("sentiment", {"risk_level": "low"})
    state.set_result(
        "decision",
        {
            "final_statement": "ok",
            "scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )
    state.add_trace(
        {
            "agent": "legal",
            "status": "success",
            "rag": {
                "retrieval_status": "skipped_by_gate",
                "evidence_quality": {
                    "evaluated": False,
                    "status": "not_applicable",
                    "reason": "retrieval_skipped",
                    "should_trigger_human_review": False,
                },
            },
        }
    )

    policy = evaluate_human_policy(state, {"passed": True, "issues": []})

    assert policy["required"] is False
    assert "rag_evidence_low_confidence" not in policy["triggers"]


def _successful_execution(state: AgentState, risk_level: str):
    state.set_result("sentiment", {"risk_level": risk_level})
    state.set_result(
        "decision",
        {
            "final_statement": "ok",
            "scores": {
                "legal_safety": 8,
                "empathy": 8,
                "robustness": 8,
            },
        },
    )
    state.add_trace(
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
        "plan_id": state.plan_id,
        "executed_agents": ["decision"],
        "results": state.get_all_results(),
        "failed_agents": [],
        "execution_trace": list(state.trace),
    }
