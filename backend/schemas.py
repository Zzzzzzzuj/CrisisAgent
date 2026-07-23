from typing import Any

from pydantic import BaseModel, Field


class CrisisRunRequest(BaseModel):
    event: str = Field(..., min_length=1, description="Crisis event description")


class AgentTraceItem(BaseModel):
    agent: str
    name: str
    input: Any
    output: Any
    start_time: str
    end_time: str
    status: str
    mode: str
    fallback: bool
    rag: dict[str, Any] | None = None


class ScoreBundle(BaseModel):
    legal_safety: int = Field(..., ge=0, le=10)
    empathy: int = Field(..., ge=0, le=10)
    robustness: int = Field(..., ge=0, le=10)


class CrisisRunResponse(BaseModel):
    session_id: str
    final_statement: str
    scores: ScoreBundle
    agent_trace: list[AgentTraceItem]
