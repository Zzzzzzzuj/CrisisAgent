import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.core.checkpoint import list_checkpoints, load_checkpoint, save_checkpoint
from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.human import approve, reject
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, RUNNING, AgentState
from backend.core.resume import resume_agent_loop
from backend.core.runtime_tasks import (
    create_queued_dynamic_session,
    is_async_runtime_enabled,
    submit_dynamic_session,
    submit_resume_session,
)
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
def run_dynamic(request: dict) -> dict:
    event = str(request.get("event", "")).strip()
    if not event:
        raise HTTPException(status_code=422, detail="Field 'event' is required.")

    if is_async_runtime_enabled():
        state = create_queued_dynamic_session(event)
        submit_dynamic_session(state.session_id)
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
        }

    result = run_dynamic_agent(event)
    state = _state_from_dynamic_result(result)
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
    }


@app.get("/api/dynamic/sessions")
def get_dynamic_sessions() -> list[dict]:
    return list_checkpoints()


@app.get("/api/dynamic/{session_id}/metrics")
def get_dynamic_metrics(session_id: str) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    return _build_dynamic_metrics(state)


@app.get("/api/dynamic/{session_id}")
def get_dynamic_session(session_id: str) -> dict:
    state = load_checkpoint(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Dynamic session '{session_id}' not found.")
    data = state.to_dict()
    data["trace"] = _enhance_trace(data.get("trace", []))
    return data


@app.post("/api/dynamic/{session_id}/approve")
def approve_dynamic_session(session_id: str, request: dict | None = None) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    body = request or {}
    try:
        approve(
            state,
            reviewer=str(body.get("reviewer", "human")),
            comment=str(body.get("comment", "")),
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
def reject_dynamic_session(session_id: str, request: dict | None = None) -> dict:
    state = _load_dynamic_state_or_404(session_id)
    body = request or {}
    try:
        reject(
            state,
            reviewer=str(body.get("reviewer", "human")),
            comment=str(body.get("comment", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_checkpoint(state)
    return resume_agent_loop(session_id)


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
