from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.runtime_tasks import run_dynamic_session_task, run_resume_session_task
from backend.core.state import AgentState, COMPLETED, FAILED, QUEUED, RUNNING
from backend.db import repositories
from backend.db.repositories import JSONCheckpointRepository, SQLAlchemyCheckpointRepository, StaleExecutionLease, use_execution_lease
from backend.db.session import Base


@pytest.fixture
def db_repository(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leases.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv("CHECKPOINT_STORAGE", "database")
    monkeypatch.setattr(repositories, "get_session_factory", lambda: factory)
    yield SQLAlchemyCheckpointRepository(factory)
    engine.dispose()


def _queued(session_id):
    state = AgentState(session_id=session_id, plan_id="", event="offline event")
    state.set_status(QUEUED)
    save_checkpoint(state)
    return state


def test_two_workers_atomically_claim_only_once(db_repository):
    _queued("concurrent")
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=5)
        return db_repository.claim_execution("concurrent", "dynamic")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(attempt)
        second = pool.submit(attempt)
        claims = [first.result(timeout=10), second.result(timeout=10)]

    assert sum(claim is not None for claim in claims) == 1
    assert next(claim for claim in claims if claim is not None).fence == 1


def test_active_lease_cannot_be_stolen_and_expired_lease_is_fenced(db_repository):
    state = _queued("reclaim")
    now = datetime.now(timezone.utc)
    first = db_repository.claim_execution(state.session_id, "dynamic", lease_seconds=60, now=now)
    assert first is not None
    assert db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(seconds=59)) is None
    state.set_status(RUNNING)
    with pytest.raises(StaleExecutionLease):
        save_checkpoint(state)

    replacement = db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(seconds=61))
    assert replacement is not None
    assert replacement.owner != first.owner
    assert replacement.fence == first.fence + 1

    state.set_result("decision", {"final_statement": "stale result"})
    with use_execution_lease(first), pytest.raises(StaleExecutionLease):
        save_checkpoint(state)
    stale_failure = AgentState.from_dict(state.to_dict())
    stale_failure.set_status(FAILED)
    with use_execution_lease(first), pytest.raises(StaleExecutionLease):
        save_checkpoint(stale_failure)
    assert load_checkpoint(state.session_id).get_result("decision") is None

    with use_execution_lease(replacement):
        state.set_result("decision", {"final_statement": "new owner"})
        state.set_status(COMPLETED)
        save_checkpoint(state)
    assert load_checkpoint(state.session_id).get_result("decision")["final_statement"] == "new owner"
    assert db_repository.claim_execution(state.session_id, "dynamic", now=now + timedelta(days=1)) is None


def test_duplicate_queued_work_runs_only_once(db_repository, monkeypatch):
    _queued("duplicate-dynamic")
    started = Event()
    release = Event()
    calls = []

    def execute(state):
        calls.append(state.session_id)
        started.set()
        assert release.wait(timeout=5)
        return {"session_id": state.session_id, "results": {}}

    monkeypatch.setattr("backend.core.runtime_tasks.execute_dynamic_state", execute)
    monkeypatch.setattr("backend.core.runtime_tasks.evaluate_runtime_state", lambda state: {"passed": True})
    monkeypatch.setattr("backend.core.runtime_tasks.evaluate_human_policy", lambda state, evaluation: {"required": False})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_dynamic_session_task, "duplicate-dynamic")
        assert started.wait(timeout=5)
        second = pool.submit(run_dynamic_session_task, "duplicate-dynamic")
        assert second.result(timeout=5)["status"] == "skipped"
        release.set()
        assert first.result(timeout=5)["status"] == "completed"
    assert calls == ["duplicate-dynamic"]


def test_duplicate_human_fact_resume_has_one_effective_worker(db_repository, monkeypatch):
    state = AgentState(session_id="duplicate-resume", plan_id="plan", event="offline event")
    state.set_status(RUNNING)
    state.metadata["human_fact"] = {"response": {"request_id": "request-1", "response_type": "FACT_UNAVAILABLE"}}
    save_checkpoint(state)
    started = Event()
    release = Event()
    calls = []

    def resume(session_id, response):
        calls.append(session_id)
        started.set()
        assert release.wait(timeout=5)
        saved = load_checkpoint(session_id)
        saved.set_status(COMPLETED)
        save_checkpoint(saved)
        return {"session_id": session_id, "status": "completed"}

    monkeypatch.setattr("backend.core.human_fact_resume.submit_human_fact_response", resume)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_resume_session_task, state.session_id)
        assert started.wait(timeout=5)
        second = pool.submit(run_resume_session_task, state.session_id)
        assert second.result(timeout=5)["status"] == "skipped"
        release.set()
        assert first.result(timeout=5)["status"] == "completed"
    assert calls == [state.session_id]


def test_approved_review_is_claimed_only_as_resume(db_repository):
    state = AgentState(session_id="approved-review", plan_id="plan", event="offline event")
    state.set_status(RUNNING)
    state.approval["decision"] = "approved"
    save_checkpoint(state)

    assert db_repository.claim_execution(state.session_id, "dynamic") is None
    assert db_repository.claim_execution(state.session_id, "resume") is not None


def test_json_repository_explicitly_does_not_support_multi_worker_claim(tmp_path):
    repository = JSONCheckpointRepository(tmp_path / "checkpoints.json")
    with pytest.raises(NotImplementedError, match="DB-backed"):
        repository.claim_execution("local-session", "dynamic")
