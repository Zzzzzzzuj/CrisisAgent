import os
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    is_auth_enabled,
    require_reviewer,
    user_to_claims,
)
from backend.core.checkpoint import list_checkpoints, load_checkpoint, save_checkpoint
from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.followup import build_followup_response
from backend.core.guardrail_runtime import apply_guardrails_to_state
from backend.core.human import approve, reject
from backend.core.policy import evaluate_human_policy
from backend.core.reasoning_mode import apply_reasoning_mode_to_state
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, RUNNING, AgentState
from backend.core.resume import resume_agent_loop
from backend.core.runtime_tasks import (
    create_queued_dynamic_session,
    is_async_runtime_enabled,
    submit_dynamic_session,
    submit_resume_session,
)
from backend.db.session import get_db_session
from backend.observability.metrics import collect_runtime_metrics
from backend.observability.readiness import check_readiness
from backend.schemas import CrisisRunRequest, CrisisRunResponse
from backend.storage import get_session, list_sessions
from backend.workflow import run_crisis_workflow


def _read_cors_origins() -> list[str]:
    raw_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


app = FastAPI(title="CrisisAgent MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_read_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def readiness_check() -> dict:
    result = check_readiness()
    if not result["ready"]:
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/api/metrics/runtime")
def get_runtime_metrics(current_user: dict | None = Depends(get_current_user)) -> dict:
    if is_auth_enabled() and (current_user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Runtime metrics require admin role.")
    return collect_runtime_metrics()


@app.post("/api/auth/login")
def login(request: dict, db: Session = Depends(get_db_session)) -> dict:
    username = str(request.get("username", "")).strip()
    password = str(request.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=422, detail="username and password are required.")
    user = authenticate_user(db, username, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": user_to_claims(user),
    }


@app.get("/api/auth/me")
def auth_me(current_user: dict | None = Depends(get_current_user)) -> dict:
    if not is_auth_enabled():
        return {"auth_enabled": False, "user": None}
    return {"auth_enabled": True, "user": current_user}


@app.post("/api/crisis/run", response_model=CrisisRunResponse)
def run_crisis(request: CrisisRunRequest) -> CrisisRunResponse:
    return run_crisis_workflow(request)


@app.get("/api/crisis/sessions")
def get_crisis_sessions() -> list[dict]:
    return list_sessions()


@app.get("/api/crisis/sessions/{session_id}")
def get_crisis_session(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


@app.post("/api/dynamic/run")
def run_dynamic(request: dict, current_user: dict | None = Depends(get_current_user)) -> dict:
    event = str(request.get("event", "")).strip()
    if not event:
        raise HTTPException(status_code=422, detail="Field 'event' is required.")

    if is_async_runtime_enabled():
        state = create_queued_dynamic_session(event, created_by=current_user)
        submit_dynamic_session(state.session_id)
        reasoning = state.metadata.get("reasoning_mode", {})
        return {
            "session_id": state.session_id,
            "plan_id": state.plan_id,
            "event": state.event,
            "status": "queued",
            "state_status": state.status,
            "approval": dict(state.approval),
            "execution_trace": [],
            "results": {},
            "failed_agents": [],
            "selected_reasoning_mode": reasoning.get("selected_reasoning_mode"),
            "reasoning_mode_reason": reasoning.get("reasoning_mode_reason", []),
            "recommended_execution_policy": reasoning.get("recommended_execution_policy", {}),
        }

    result = run_dynamic_agent(event)
    state = _state_from_dynamic_result(result)
    _record_created_by(state, current_user)
    apply_guardrails_to_state(state)
    apply_reasoning_mode_to_state(
        state,
        user_requested_strict_review=bool(request.get("strict_review", False)),
    )
    evaluation = evaluate_runtime_state(state)
    policy = evaluate_human_policy(state, evaluation)

    if policy.get("required"):
        from backend.core.human import request_review

        request_review(state, policy.get("reason", "Human review required."))
        status = "waiting_human"
    else:
        state.status = COMPLETED
        status = "completed"

    save_checkpoint(state)
    response_trace = _enhance_trace(state.trace)
    return {
        **result,
        "execution_trace": response_trace,
        "status": status,
        "state_status": state.status,
        "approval": dict(state.approval),
        "evaluation": evaluation,
        "policy": policy,
        "selected_reasoning_mode": state.metadata.get("reasoning_mode", {}).get("selected_reasoning_mode"),
        "reasoning_mode_reason": state.metadata.get("reasoning_mode", {}).get("reasoning_mode_reason", []),
        "recommended_execution_policy": state.metadata.get("reasoning_mode", {}).get("recommended_execution_policy", {}),
    }


@app.get("/api/dynamic/sessions")
def get_dynamic_sessions(current_user: dict | None = Depends(get_current_user)) -> list[dict]:
    sessions = list_checkpoints()
    if not is_auth_enabled() or current_user is None or current_user.get("role") in {"admin", "legal_reviewer"}:
        return sessions
    return [
        session
        for session in sessions
        if (session.get("created_by") or {}).get("id") == current_user.get("id")
    ]


@app.get("/api/dynamic/{session_id}/metrics")
def get_dynamic_metrics(session_id: str, current_user: dict | None = Depends(get_current_user)) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    _ensure_session_access(state, current_user)
    return _build_dynamic_metrics(state)


@app.get("/api/dynamic/{session_id}")
def get_dynamic_session(session_id: str, current_user: dict | None = Depends(get_current_user)) -> dict:
    state = load_checkpoint(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Dynamic session '{session_id}' not found.")
    _ensure_session_access(state, current_user)
    data = state.to_dict()
    data["trace"] = _enhance_trace(data.get("trace", []))
    return data


@app.post("/api/dynamic/{session_id}/followup")
def dynamic_followup(
    session_id: str,
    request: dict,
    current_user: dict | None = Depends(get_current_user),
) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    _ensure_session_access(state, current_user)
    try:
        return build_followup_response(
            state,
            question=str(request.get("question", "")),
            followup_type=str(request.get("followup_type", "clarification")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/dynamic/{session_id}/approve")
def approve_dynamic_session(
    session_id: str,
    request: dict | None = None,
    current_user: dict | None = Depends(require_reviewer),
) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    body = request or {}
    try:
        reviewer_identity = _reviewer_identity(body, current_user)
        approve(
            state,
            reviewer=reviewer_identity["reviewer"],
            comment=str(body.get("comment", "")),
            reviewer_id=reviewer_identity["reviewer_id"],
            reviewer_username=reviewer_identity["reviewer_username"],
            reviewer_role=reviewer_identity["reviewer_role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_checkpoint(state)
    if is_async_runtime_enabled():
        submit_resume_session(session_id)
        return {
            "session_id": session_id,
            "status": "queued",
            "state_status": state.status,
            "approval": dict(state.approval),
        }
    return resume_agent_loop(session_id)


@app.post("/api/dynamic/{session_id}/reject")
def reject_dynamic_session(
    session_id: str,
    request: dict | None = None,
    current_user: dict | None = Depends(require_reviewer),
) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    body = request or {}
    try:
        reviewer_identity = _reviewer_identity(body, current_user)
        reject(
            state,
            reviewer=reviewer_identity["reviewer"],
            comment=str(body.get("comment", "")),
            reviewer_id=reviewer_identity["reviewer_id"],
            reviewer_username=reviewer_identity["reviewer_username"],
            reviewer_role=reviewer_identity["reviewer_role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_checkpoint(state)
    return resume_agent_loop(session_id)


def _record_created_by(state: AgentState, current_user: dict | None) -> None:
    if not is_auth_enabled() or current_user is None:
        return
    state.metadata["created_by"] = {
        "id": current_user.get("id"),
        "username": current_user.get("username", ""),
        "role": current_user.get("role", ""),
    }


def _reviewer_identity(body: dict, current_user: dict | None) -> dict:
    if not is_auth_enabled() or current_user is None:
        reviewer = str(body.get("reviewer", "human"))
        return {
            "reviewer": reviewer,
            "reviewer_id": None,
            "reviewer_username": reviewer,
            "reviewer_role": "",
        }
    return {
        "reviewer": str(current_user.get("username", "")),
        "reviewer_id": current_user.get("id"),
        "reviewer_username": str(current_user.get("username", "")),
        "reviewer_role": str(current_user.get("role", "")),
    }


def _ensure_session_access(state: AgentState, current_user: dict | None) -> None:
    if not is_auth_enabled() or current_user is None:
        return
    if current_user.get("role") in {"admin", "legal_reviewer"}:
        return
    created_by = state.metadata.get("created_by", {})
    if isinstance(created_by, dict) and created_by.get("id") == current_user.get("id"):
        return
    raise HTTPException(status_code=403, detail="Session access denied.")


def _load_dynamic_state_or_404(session_id: str) -> AgentState:
    state = load_checkpoint(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Dynamic session '{session_id}' not found.")
    return state


def _state_from_dynamic_result(result: dict) -> AgentState:
    state = AgentState(
        session_id=result["session_id"],
        plan_id=result.get("plan_id", ""),
        event=result.get("event", ""),
        results=result.get("results", {}),
        trace=result.get("execution_trace", []),
        metadata={
            "planner_input": result.get("planner_input", {}),
            "raw_plan": result.get("raw_plan", {}),
            "validated_plan": result.get("validated_plan", {}),
        },
    )
    state.failed_agents = list(result.get("failed_agents", []))
    state.status = RUNNING
    return state


def _enhance_trace(trace: list[dict]) -> list[dict]:
    return [_enhance_trace_item(item) for item in trace]


def _enhance_trace_item(item: dict) -> dict:
    enhanced = dict(item)
    enhanced.setdefault("start_time", item.get("start_time"))
    enhanced.setdefault("end_time", item.get("end_time"))
    enhanced["duration_ms"] = _duration_ms(
        enhanced.get("start_time"),
        enhanced.get("end_time"),
    )
    enhanced["input_summary"] = _summarize_value(
        item.get("input", item.get("payload", item.get("reason", "")))
    )
    enhanced["output_summary"] = _summarize_value(item.get("output"))
    enhanced["error"] = item.get("error")
    return enhanced


def _build_dynamic_metrics(state: AgentState) -> dict:
    trace = _enhance_trace(state.trace)
    total_duration = sum(item.get("duration_ms") or 0 for item in trace)
    trace_failed_agents = [
        item.get("agent")
        for item in trace
        if item.get("status") == "failed" and item.get("agent")
    ]
    tool_calls = 0
    for item in trace:
        tools = item.get("tools", [])
        if isinstance(tools, list):
            tool_calls += len(tools)

    return {
        "session_id": state.session_id,
        "total_duration": total_duration,
        "agent_count": len(trace),
        "failed_agents": _unique_list(
            [item.get("agent") for item in state.failed_agents if isinstance(item, dict)]
            + trace_failed_agents
        ),
        "rag_hits": sum(1 for item in trace if (item.get("rag") or {}).get("hit")),
        "memory_hits": sum(1 for item in trace if (item.get("memory") or {}).get("hit")),
        "tool_calls": tool_calls,
        "human_status": {
            "state_status": state.status,
            "required": state.approval.get("required"),
            "decision": state.approval.get("decision"),
            "reason": state.approval.get("reason"),
        },
    }


def _duration_ms(start_time: str | None, end_time: str | None) -> int:
    if not start_time or not end_time:
        return 0
    try:
        start = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def _summarize_value(value: Any, max_length: int = 160) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _unique_list(values: list) -> list:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
