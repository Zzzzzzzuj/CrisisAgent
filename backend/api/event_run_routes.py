from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_schemas import EventReviewResponse, EventRunRequest, EventRunResponse
from backend.api.event_store import get_crisis_event_store
from backend.core.runtime_tasks import run_dynamic_sync_with_metadata
from backend.api.workspace_security import authorize, get_workspace_user, owner_fields, write_audit


router = APIRouter(prefix="/api/events", tags=["event-agent-runs"])


@router.post("/{event_id}/run", response_model=EventRunResponse, status_code=status.HTTP_201_CREATED)
def run_event_agent(event_id: str, payload: EventRunRequest, user: dict = Depends(get_workspace_user)) -> EventRunResponse:
    authorize(user, {"admin", "operator"}, "event_agent.run", "event", event_id)
    event_store = get_crisis_event_store()
    event = event_store.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")
    if event.get("status") == "archived":
        raise HTTPException(status_code=409, detail="Archived crisis events cannot run Agent.")

    run_store = get_event_agent_run_store()
    if not payload.force_rerun:
        existing = run_store.get_latest(event_id)
        if existing is not None:
            return _run_response(existing)

    ingestion_metadata = _ingestion_metadata(event)
    event_text = _event_to_text(event)
    started_at = _now()
    event_store.update(event_id, {"status": "running"})

    try:
        with _agent_mode(payload.mode):
            result = run_dynamic_sync_with_metadata(
                event_text,
                metadata={"ingestion": ingestion_metadata},
            )
        run_status = _run_status(result)
        policy = result.get("policy") or {}
        evaluation = result.get("evaluation") or {}
        decision = (result.get("results") or {}).get("decision") or {}
        run = run_store.create(
            {
                "event_id": event_id,
                "session_id": result["session_id"],
                "status": run_status,
                "mode": payload.mode,
                "started_at": started_at,
                "finished_at": _now(),
                "final_statement_preview": _final_statement_preview(result),
                "scores": decision.get("scores", {}),
                "human_review_required": bool(policy.get("required")),
                "policy_triggers": list(policy.get("triggers", [])),
                "trace": result.get("execution_trace", []),
                "evaluation": evaluation,
                "metadata": {"ingestion": ingestion_metadata},
                "error": None,
                "automatic_publish": False,
                **owner_fields(user),
            }
        )
        event_store.update(event_id, {"status": run_status})
    except Exception as exc:
        run = run_store.create(
            {
                "event_id": event_id,
                "session_id": "",
                "status": "failed",
                "mode": payload.mode,
                "started_at": started_at,
                "finished_at": _now(),
                "final_statement_preview": "",
                "scores": {},
                "human_review_required": bool(event.get("human_review_required")),
                "policy_triggers": [],
                "trace": [],
                "metadata": {"ingestion": ingestion_metadata},
                "error": str(exc),
                "automatic_publish": False,
                **owner_fields(user),
            }
        )
        event_store.update(event_id, {"status": "failed"})

    write_audit(user, "event_agent.run", "event_agent_run", run["agent_run_id"])
    return _run_response(run)


@router.get("/{event_id}/run", response_model=EventRunResponse)
def get_event_run(event_id: str, user: dict = Depends(get_workspace_user)) -> EventRunResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "event_agent.view", "event", event_id)
    _ensure_event_exists(event_id)
    run = get_event_agent_run_store().get_latest(event_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No Agent run found for event '{event_id}'.")
    return _run_response(run)


@router.get("/{event_id}/trace")
def get_event_trace(event_id: str, user: dict = Depends(get_workspace_user)) -> dict[str, Any]:
    authorize(user, {"admin", "operator", "legal_reviewer"}, "event_agent.trace.view", "event", event_id)
    _ensure_event_exists(event_id)
    run = get_event_agent_run_store().get_latest(event_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No Agent run found for event '{event_id}'.")
    write_audit(user, "event_agent.trace.view", "event_agent_run", run["agent_run_id"])
    return {
        "event_id": event_id,
        "agent_run_id": run["agent_run_id"],
        "session_id": run.get("session_id", ""),
        "trace": run.get("trace", []),
        "metadata": run.get("metadata", {}),
        "evaluation": run.get("evaluation", {}),
        "policy_triggers": run.get("policy_triggers", []),
    }


@router.get("/{event_id}/review", response_model=EventReviewResponse)
def get_event_review(event_id: str, user: dict = Depends(get_workspace_user)) -> EventReviewResponse:
    authorize(user, {"admin", "operator", "legal_reviewer"}, "event_agent.review.view", "event", event_id)
    _ensure_event_exists(event_id)
    run = get_event_agent_run_store().get_latest(event_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No Agent run found for event '{event_id}'.")
    needs_review = bool(run.get("human_review_required", False))
    triggers = list(run.get("policy_triggers", []))
    write_audit(user, "event_agent.review.view", "event_agent_run", run["agent_run_id"])
    return EventReviewResponse(
        event_id=event_id,
        session_id=run.get("session_id", ""),
        status=run.get("status", "failed"),
        human_review_required=needs_review,
        approval_status="pending" if needs_review else None,
        policy_triggers=triggers,
        review_reason=("Human review required: " + ", ".join(triggers)) if needs_review else "",
        allowed_actions=["approve", "reject", "request_revision"] if needs_review else [],
    )


def _ensure_event_exists(event_id: str) -> None:
    if get_crisis_event_store().get(event_id) is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")


def _run_response(run: dict[str, Any]) -> EventRunResponse:
    return EventRunResponse(
        event_id=run["event_id"],
        agent_run_id=run["agent_run_id"],
        session_id=run.get("session_id", ""),
        status=run.get("status", "failed"),
        final_statement_preview=run.get("final_statement_preview", ""),
        scores=run.get("scores", {}),
        human_review_required=bool(run.get("human_review_required", False)),
        policy_triggers=list(run.get("policy_triggers", [])),
        trace_count=len(run.get("trace", [])),
        automatic_publish=False,
        created_by=run.get("created_by"),
        owner_id=run.get("owner_id"),
    )


def _ingestion_metadata(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_items": list(event.get("source_items", [])),
        "source_count": event.get("source_count", 0),
        "risk_level": event.get("risk_level", ""),
        "fact_status": event.get("fact_status", ""),
        "event_status": event.get("event_status", ""),
        "human_review_required": bool(event.get("human_review_required", False)),
        "event_fingerprint": event.get("event_fingerprint", ""),
    }


def _event_to_text(event: dict[str, Any]) -> str:
    return (
        f"公司：{event.get('company', '')}\n"
        f"事件：{event.get('event_summary') or event.get('title', '')}\n"
        f"风险等级：{event.get('risk_level', '')}\n"
        f"事实状态：{event.get('fact_status', '')}；事件状态：{event.get('event_status', '')}"
    ).strip()


def _run_status(result: dict[str, Any]) -> str:
    if result.get("status") == "waiting_human":
        return "waiting_human"
    if result.get("status") == "failed":
        return "failed"
    return "completed"


def _final_statement_preview(result: dict[str, Any]) -> str:
    decision = (result.get("results") or {}).get("decision") or {}
    value = decision.get("final_statement") or decision.get("statement") or ""
    return str(value)[:500]


@contextmanager
def _agent_mode(mode: str):
    previous = os.environ.get("AGENT_MODE")
    os.environ["AGENT_MODE"] = mode
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AGENT_MODE", None)
        else:
            os.environ["AGENT_MODE"] = previous


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
