from fastapi import FastAPI, HTTPException

from backend.schemas import CrisisRunRequest, CrisisRunResponse
from backend.storage import get_session, list_sessions
from backend.workflow import run_crisis_workflow


app = FastAPI(title="CrisisAgent MVP", version="0.1.0")


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
