from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HarnessSpecResponse(BaseModel):
    metadata: dict[str, Any]
    workflow: dict[str, Any]
    prompts: dict[str, Any]
    skills_tools: dict[str, Any]
    context_policy: dict[str, Any]
    retrieval_policy: dict[str, Any]
    review_policy: dict[str, Any]


class HarnessListResponse(BaseModel):
    harnesses: list[HarnessSpecResponse]
    count: int


class HarnessCreateRequest(BaseModel):
    spec: dict[str, Any]
    parent_version: str | None = None
    model_config = ConfigDict(extra="forbid")


class HarnessCopyRequest(BaseModel):
    new_version: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class HarnessCandidatePatchRequest(BaseModel):
    changes: dict[str, Any]
    change_summary: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class HarnessEvaluateRequest(BaseModel):
    baseline_harness_id: str = Field(..., min_length=1)
    baseline_version: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class HarnessApproveRequest(BaseModel):
    comparison_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class HarnessRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")
