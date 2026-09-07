from datetime import datetime, timezone

from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.dynamic_runtime import initialize_dynamic_state
from backend.core.human import approve, reject, request_review
from backend.core.policy import evaluate_human_policy
from backend.core.resume import resume_agent_loop
from backend.core.runtime_tasks import run_dynamic_sync, run_dynamic_sync_with_metadata
from backend.core.state import AgentState, WAITING_HUMAN
from backend.ingestion.pipeline import run_sentiment_ingestion_pipeline, to_crisis_event_text


def _ingestion_metadata(**overrides):
    data = {
        "cluster_id": "cluster_test",
        "source_items": ["source_1", "source_2"],
        "source_count": 2,
        "event_status": "current",
        "fact_status": "verified",
        "risk_level": "low",
        "human_review_required": False,
        "event_fingerprint": "company|event",
    }
    data.update(overrides)
    return data


def test_initialize_state_stores_ingestion_metadata_without_replacing_planner_input():
    state = initialize_dynamic_state("普通事件", metadata={"ingestion": _ingestion_metadata()})
    assert state.metadata["ingestion"]["source_items"] == ["source_1", "source_2"]
    assert state.metadata["planner_input"]["event"] == "普通事件"


def test_legacy_run_dynamic_sync_without_metadata_remains_compatible(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    result = run_dynamic_sync("普通企业咨询")
    assert result["session_id"]
    assert result["status"] in {"completed", "waiting_human"}


def test_ingestion_triggers_are_specific_and_composable():
    state = AgentState("session", "plan", "事件", metadata={"ingestion": _ingestion_metadata(
        human_review_required=True,
        risk_level="high",
        fact_status="conflicting",
        event_status="uncertain",
    )})
    policy = evaluate_human_policy(state, {"passed": True})
    assert policy["required"] is True
    assert {
        "ingestion_review_required",
        "ingestion_high_risk",
        "ingestion_fact_conflicting",
        "ingestion_event_uncertain",
    }.issubset(policy["triggers"])
    assert "ingestion" in policy["reason"]


def test_each_ingestion_status_can_trigger_review():
    cases = [
        ({"human_review_required": True}, "ingestion_review_required"),
        ({"risk_level": "high"}, "ingestion_high_risk"),
        ({"fact_status": "unverified"}, "ingestion_fact_unverified"),
        ({"fact_status": "conflicting"}, "ingestion_fact_conflicting"),
        ({"event_status": "uncertain"}, "ingestion_event_uncertain"),
        ({"event_status": "historical", "human_review_required": True}, "ingestion_historical_review_required"),
    ]
    for overrides, expected in cases:
        state = AgentState("session", "plan", "事件", metadata={"ingestion": _ingestion_metadata(**overrides)})
        policy = evaluate_human_policy(state, {"passed": True})
        assert expected in policy["triggers"]


def test_missing_or_malformed_ingestion_metadata_does_not_break_policy():
    for metadata in ({}, {"ingestion": None}, {"ingestion": "legacy"}, {"ingestion": {"fact_status": None}}):
        state = AgentState("session", "plan", "事件", metadata=metadata)
        policy = evaluate_human_policy(state, {"passed": True})
        assert isinstance(policy["required"], bool)


def test_runtime_enters_waiting_human_and_persists_ingestion_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    metadata = {"ingestion": _ingestion_metadata(human_review_required=True, risk_level="high")}

    import backend.core.runtime_tasks as runtime_tasks

    monkeypatch.setattr(runtime_tasks, "save_checkpoint", lambda state: state.to_dict())
    result = run_dynamic_sync_with_metadata("风险事件", metadata=metadata)
    assert result["status"] == "waiting_human"
    assert "ingestion_review_required" in result["policy"]["triggers"]

    state = initialize_dynamic_state("风险事件", metadata=metadata)
    state.set_status(WAITING_HUMAN)
    checkpoint = tmp_path / "checkpoints.json"
    save_checkpoint(state, checkpoint)
    loaded = load_checkpoint(state.session_id, checkpoint)
    assert loaded.metadata["ingestion"]["event_fingerprint"] == "company|event"


def test_approve_resume_keeps_ingestion_metadata_and_reject_blocks_resume(tmp_path):
    checkpoint = tmp_path / "checkpoints.json"
    state = initialize_dynamic_state("风险事件", metadata={"ingestion": _ingestion_metadata(human_review_required=True)})
    request_review(state, "Human review required: ingestion_review_required", policy_result={"triggers": ["ingestion_review_required"]})
    save_checkpoint(state, checkpoint)

    approve(state, reviewer="reviewer")
    save_checkpoint(state, checkpoint)
    resumed = resume_agent_loop(
        state.session_id,
        checkpoint_path=checkpoint,
        planner=lambda _: {"plan_id": "plan", "plan": []},
        validator=lambda plan: plan,
        executor=lambda plan, current, agent_registry=None: {"executed_agents": []},
        evaluator=lambda _: {"passed": True},
        policy=lambda _, __: {"required": False, "triggers": [], "reason": ""},
    )
    assert resumed["status"] == "completed"
    loaded = load_checkpoint(state.session_id, checkpoint)
    assert loaded.metadata["ingestion"]["source_count"] == 2

    rejected = initialize_dynamic_state("风险事件", metadata={"ingestion": _ingestion_metadata(human_review_required=True)})
    request_review(rejected, "Human review required: ingestion_review_required", policy_result={"triggers": ["ingestion_review_required"]})
    reject(rejected, reviewer="reviewer")
    save_checkpoint(rejected, checkpoint)
    blocked = resume_agent_loop(rejected.session_id, checkpoint_path=checkpoint)
    assert blocked["stopped_reason"] == "human_rejected"


def test_fixture_cluster_metadata_is_ready_for_the_bridge():
    fixture = "data/sentiment_ingestion_fixture.json"
    event = run_sentiment_ingestion_pipeline(fixture, datetime(2026, 9, 7, tzinfo=timezone.utc))[0]
    assert event.to_dict()["source_items"]
    assert "事实状态" in to_crisis_event_text(event)
