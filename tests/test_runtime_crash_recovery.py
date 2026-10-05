import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from time import sleep

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_targeted_search import run_legal_action_loop
from backend.core import dynamic_runtime, runtime_tasks
from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.human_fact_resume import record_human_fact_response_for_async
from backend.core.human_fact_runtime import pause_for_claim_index
from backend.core.state import AgentState, COMPLETED, FAILED, QUEUED, RUNNING, WAITING_HUMAN
from backend.db import repositories
from backend.db.models import AgentCheckpoint
from backend.db.repositories import ExecutionLease, SQLAlchemyCheckpointRepository, StaleExecutionLease, use_execution_lease
from backend.db.session import Base
from evaluation.frozen_hash import canonical_text_sha256


@pytest.fixture
def db_repository(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p4.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv("CHECKPOINT_STORAGE", "database")
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "inprocess")
    monkeypatch.setattr(repositories, "get_session_factory", lambda: factory)
    yield SQLAlchemyCheckpointRepository(factory)
    engine.dispose()


def _queued(session_id):
    state = AgentState(session_id=session_id, plan_id="", event="offline fixture")
    state.set_status(QUEUED)
    save_checkpoint(state)
    return state


def _expire(repository, session_id):
    with repository.session_factory() as db:
        db.execute(update(AgentCheckpoint).where(AgentCheckpoint.session_id == session_id).values(
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=5)))
        db.commit()


def test_frozen_fault_scenarios_have_required_boundaries():
    frozen = Path("evaluation/p4_runtime_fault_scenarios_frozen.json").read_bytes()
    assert canonical_text_sha256(frozen) == (
        "06bcd64f97ef7e456e4d015551588e60937c5b32cbfb77bbcde3b6780cb1f0a0")
    payload = json.loads(frozen)
    assert [row["id"] for row in payload["scenarios"]] == ["F1", "F2", "F3", "F4", "F5"]
    assert payload["scenarios"][-1]["duplicate_external_call_boundary"] == "at_least_once_risk_no_exactly_once_guarantee"


def test_renewal_stale_scan_and_old_worker_resurrection(db_repository):
    state = _queued("p4-fencing")
    now = datetime.now(timezone.utc)
    first = db_repository.claim_execution(state.session_id, "dynamic", lease_seconds=60, now=now)
    assert first and first.fence == 1
    assert db_repository.find_stale_executions(now=now + timedelta(seconds=30)) == []
    assert db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(seconds=30)) is None
    renewed = db_repository.renew_execution(first, lease_seconds=60, now=now + timedelta(seconds=30))
    assert renewed and renewed.owner == first.owner and renewed.fence == first.fence
    assert renewed.expires_at == now + timedelta(seconds=90)
    assert db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(seconds=61)) is None
    assert db_repository.find_stale_executions(now=now + timedelta(seconds=91))[0]["session_id"] == state.session_id
    second = db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(seconds=91))
    assert second and second.owner != first.owner and second.fence == first.fence + 1
    assert db_repository.renew_execution(first, now=now + timedelta(seconds=92)) is None

    state.set_status(RUNNING)
    with use_execution_lease(first), pytest.raises(StaleExecutionLease):
        save_checkpoint(state)
    state.set_status(COMPLETED)
    with use_execution_lease(first), pytest.raises(StaleExecutionLease):
        save_checkpoint(state)
    failed = AgentState.from_dict(state.to_dict())
    failed.status = FAILED
    with use_execution_lease(first), pytest.raises(StaleExecutionLease):
        save_checkpoint(failed)
    assert load_checkpoint(state.session_id).status == QUEUED
    with use_execution_lease(second):
        save_checkpoint(state)
    assert load_checkpoint(state.session_id).status == COMPLETED
    assert db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(days=1)) is None


def test_crash_after_claim_recovery_scan_and_duplicate_scan(db_repository, monkeypatch):
    state = _queued("p4-after-claim")
    first = db_repository.claim_execution(state.session_id, "dynamic")
    assert first and db_repository.find_stale_executions() == []
    _expire(db_repository, state.session_id)
    monkeypatch.setattr(runtime_tasks, "execute_dynamic_state", lambda saved, *, checkpoint: {"session_id": saved.session_id})
    monkeypatch.setattr(runtime_tasks, "evaluate_runtime_state", lambda saved: {"passed": True})
    monkeypatch.setattr(runtime_tasks, "evaluate_human_policy", lambda saved, evaluation: {"required": False})
    dispatched = []
    monkeypatch.setattr(runtime_tasks, "submit_dynamic_session",
                        lambda session_id: dispatched.append(runtime_tasks.run_dynamic_session_task(session_id)))
    assert runtime_tasks.recover_stale_executions() == [{"session_id": state.session_id, "kind": "dynamic"}]
    assert dispatched[0]["status"] == "completed"
    assert runtime_tasks.recover_stale_executions() == []
    assert load_checkpoint(state.session_id).status == COMPLETED
    with db_repository.session_factory() as db:
        row = db.get(AgentCheckpoint, state.session_id)
        assert row.execution_fence == first.fence + 1
        assert row.execution_owner is None


def test_unclaimed_queued_session_is_visible_to_recovery_scan(db_repository):
    state = _queued("p4-before-claim")
    assert db_repository.find_stale_executions() == [
        {"session_id": state.session_id, "kind": "dynamic", "status": QUEUED, "fence": 0}]


def test_heartbeat_keeps_active_work_from_being_reclaimed(db_repository, monkeypatch):
    state = _queued("p4-heartbeat")
    monkeypatch.setenv("RUNTIME_EXECUTION_LEASE_SECONDS", "2")
    started = Event()
    release = Event()

    def execute(saved, *, checkpoint):
        started.set()
        assert release.wait(timeout=8)
        return {"session_id": saved.session_id}

    monkeypatch.setattr(runtime_tasks, "execute_dynamic_state", execute)
    monkeypatch.setattr(runtime_tasks, "evaluate_runtime_state", lambda saved: {"passed": True})
    monkeypatch.setattr(runtime_tasks, "evaluate_human_policy", lambda saved, evaluation: {"required": False})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runtime_tasks.run_dynamic_session_task, state.session_id)
        assert started.wait(timeout=5)
        sleep(2.5)
        assert db_repository.find_stale_executions() == []
        assert db_repository.claim_execution(state.session_id, "dynamic") is None
        release.set()
        assert future.result(timeout=5)["status"] == "completed"


def test_duplicate_recovery_scans_dispatch_but_only_one_claim_succeeds(db_repository, monkeypatch):
    state = _queued("p4-double-scan")
    first = db_repository.claim_execution(state.session_id, "dynamic")
    assert first
    _expire(db_repository, state.session_id)
    dispatches = []
    monkeypatch.setattr(runtime_tasks, "submit_dynamic_session", lambda session_id: dispatches.append(session_id))
    runtime_tasks.recover_stale_executions()
    runtime_tasks.recover_stale_executions()
    assert dispatches == [state.session_id, state.session_id]
    monkeypatch.setattr(runtime_tasks, "execute_dynamic_state", lambda saved, *, checkpoint: {"session_id": saved.session_id})
    monkeypatch.setattr(runtime_tasks, "evaluate_runtime_state", lambda saved: {"passed": True})
    monkeypatch.setattr(runtime_tasks, "evaluate_human_policy", lambda saved, evaluation: {"required": False})
    assert runtime_tasks.run_dynamic_session_task(state.session_id)["status"] == "completed"
    assert runtime_tasks.run_dynamic_session_task(state.session_id)["status"] == "skipped"


def test_checkpoint_resume_skips_completed_step_and_preserves_snapshots(db_repository, monkeypatch):
    owners = iter(("worker-a", "worker-b"))
    monkeypatch.setattr(repositories, "uuid4", lambda: next(owners))
    state = _queued("p4-after-step")
    state.metadata["context_pack_snapshots"] = {"sentiment": {"snapshot_id": "safe-snapshot"}}
    state.metadata["legal_action_loop"] = {"cursor": {"round_count": 2, "tool_calls_used": 1}}
    save_checkpoint(state)
    calls = {"planner": 0, "sentiment": 0, "writer": 0}

    def plan(_payload):
        calls["planner"] += 1
        return {"plan_id": "p4-plan", "plan": [{"agent": "writer"}]}

    def sentiment(_payload):
        calls["sentiment"] += 1
        return {"risk_level": "low"}

    def writer(_payload):
        calls["writer"] += 1
        return {"statement": "uncertain fixture"}

    monkeypatch.setattr(dynamic_runtime.planner_agent, "run", plan)
    real_execute = dynamic_runtime.execute_dynamic_state
    crash_once = True

    def execute(saved, *, checkpoint):
        def injected_checkpoint(step_state):
            nonlocal crash_once
            checkpoint(step_state)
            if crash_once and step_state.get_result("sentiment") and not step_state.get_result("writer"):
                crash_once = False
                raise SystemExit("injected worker death after safe checkpoint")

        return real_execute(saved, agent_registry={"sentiment": sentiment, "writer": writer},
                            checkpoint=injected_checkpoint)

    monkeypatch.setattr(runtime_tasks, "execute_dynamic_state", execute)
    monkeypatch.setattr(runtime_tasks, "evaluate_runtime_state", lambda saved: {"passed": True})
    monkeypatch.setattr(runtime_tasks, "evaluate_human_policy", lambda saved, evaluation: {"required": False})
    with pytest.raises(SystemExit, match="injected worker death"):
        runtime_tasks.run_dynamic_session_task(state.session_id)
    persisted = load_checkpoint(state.session_id)
    assert persisted.status == RUNNING
    assert persisted.get_result("sentiment") and persisted.get_result("writer") is None
    assert persisted.metadata["context_pack_snapshots"] == state.metadata["context_pack_snapshots"]
    assert persisted.metadata["legal_action_loop"] == state.metadata["legal_action_loop"]
    assert calls == {"planner": 1, "sentiment": 1, "writer": 0}

    with db_repository.session_factory() as db:
        claimed = db.get(AgentCheckpoint, state.session_id)
        assert (claimed.execution_owner, claimed.execution_fence) == ("worker-a", 1)

    _expire(db_repository, state.session_id)
    dispatched = []
    monkeypatch.setattr(runtime_tasks, "submit_dynamic_session",
                        lambda session_id: dispatched.append(runtime_tasks.run_dynamic_session_task(session_id)))
    assert runtime_tasks.recover_stale_executions()[0]["session_id"] == state.session_id
    assert dispatched[0]["status"] == "completed"
    assert calls == {"planner": 1, "sentiment": 1, "writer": 1}
    final = load_checkpoint(state.session_id)
    assert final.status == COMPLETED
    assert final.metadata["context_pack_snapshots"] == state.metadata["context_pack_snapshots"]
    assert final.metadata["legal_action_loop"] == state.metadata["legal_action_loop"]
    with db_repository.session_factory() as db:
        reclaimed = db.get(AgentCheckpoint, state.session_id)
        assert (reclaimed.execution_owner, reclaimed.execution_fence) == (None, 2)
    old_lease = ExecutionLease(state.session_id, "worker-a", 1, datetime.now(timezone.utc))
    with use_execution_lease(old_lease), pytest.raises(StaleExecutionLease):
        save_checkpoint(persisted)


def test_human_fact_response_survives_resume_claim_crash(db_repository, monkeypatch):
    owners = iter(("worker-a", "worker-b"))
    monkeypatch.setattr(repositories, "uuid4", lambda: next(owners))
    state = AgentState(session_id="p4-human-fact", plan_id="p4", event="offline fixture")
    state.set_status(RUNNING)
    claim = "本批次情况尚未确认"
    state.set_result("writer", {"statement": claim})
    extraction = {"legal_claims": [{"claim": claim, "requires_case_fact": True,
                                    "requires_legal_rule": False}], "claim_extraction_status": "ok"}
    relation = {"legal_claim_relations": [{"claim_index": 0, "evidence_ref": "none",
                                           "relation": "no_rule_match"}], "relation_status": "ok"}
    coverage = build_claim_coverage(extraction["legal_claims"], relation)
    loop = run_legal_action_loop(extraction, coverage, relation,
                                 {"retrieval_status": "not_executed", "retrieval_executed": False},
                                 mode="mock", retrieve_call=lambda *_a, **_k: pytest.fail("no legal retrieval"))
    assert loop["stop_reason"] == "human_fact_required"
    state.metadata["legal_claim_extraction"] = extraction
    state.metadata["legal_claim_coverage"] = loop["claim_coverage"]
    state.metadata["legal_action_loop"] = loop
    assert pause_for_claim_index(state, [], 0)
    request_id = state.metadata["human_fact"]["request"]["request_id"]
    save_checkpoint(state)
    response = {"request_id": request_id, "response_type": "FACT_PROVIDED", "fact_text": "test-only human assertion"}
    record_human_fact_response_for_async(state.session_id, response)
    assert db_repository.find_stale_executions()[0]["kind"] == "resume"
    first = db_repository.claim_execution(state.session_id, "resume")
    assert first and (first.owner, first.fence) == ("worker-a", 1)
    assert load_checkpoint(state.session_id).metadata["human_fact"]["response"] == response
    _expire(db_repository, state.session_id)
    dispatched = []
    monkeypatch.setattr(runtime_tasks, "submit_resume_session",
                        lambda session_id: dispatched.append(runtime_tasks.run_resume_session_task(session_id)))
    assert runtime_tasks.recover_stale_executions() == [{"session_id": state.session_id, "kind": "resume"}]
    assert dispatched[0]["state_status"] == WAITING_HUMAN
    final = load_checkpoint(state.session_id)
    assert final.metadata["human_fact"]["response"] == response
    assert final.metadata["human_fact"]["phase"] == "COMPLETED"
    assert final.metadata["human_wait_type"] == "FINAL_REVIEW"
    assert final.metadata["legal_action_loop"]["cursor"]["consumed_request_ids"] == [request_id]
    assert sum(item.get("agent") == "human_fact" and item.get("action") == "HUMAN_FACT_RESPONSE"
               for item in final.trace) == 1
    assert runtime_tasks.recover_stale_executions() == []
    with db_repository.session_factory() as db:
        reclaimed = db.get(AgentCheckpoint, state.session_id)
        assert reclaimed.execution_fence == 2


def test_external_call_before_checkpoint_can_repeat_after_reclaim(db_repository, monkeypatch):
    state = _queued("p4-ambiguous-call")
    calls = []

    def execute(saved, *, checkpoint):
        calls.append("simulated_external_call")
        if len(calls) == 1:
            raise SystemExit("injected death after request before persistence")
        saved.set_result("writer", {"statement": "offline result"})
        checkpoint(saved)
        return {"session_id": saved.session_id}

    monkeypatch.setattr(runtime_tasks, "execute_dynamic_state", execute)
    monkeypatch.setattr(runtime_tasks, "evaluate_runtime_state", lambda saved: {"passed": True})
    monkeypatch.setattr(runtime_tasks, "evaluate_human_policy", lambda saved, evaluation: {"required": False})
    with pytest.raises(SystemExit, match="injected death"):
        runtime_tasks.run_dynamic_session_task(state.session_id)
    assert load_checkpoint(state.session_id).get_result("writer") is None
    _expire(db_repository, state.session_id)
    monkeypatch.setattr(runtime_tasks, "submit_dynamic_session", runtime_tasks.run_dynamic_session_task)
    assert runtime_tasks.recover_stale_executions()[0]["session_id"] == state.session_id
    assert calls == ["simulated_external_call", "simulated_external_call"]
    assert load_checkpoint(state.session_id).status == COMPLETED
