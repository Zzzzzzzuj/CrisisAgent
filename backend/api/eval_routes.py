from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.eval_schemas import (
    EvalOverviewResponse,
    EvalRegressionResponse,
    EvalRunListItem,
    EvalRunListResponse,
    EvalRunRequest,
    EvalRunResponse,
)
from backend.api.eval_service import build_eval_overview, build_eval_run, build_regression
from backend.api.eval_store import get_eval_run_store
from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_store import get_crisis_event_store
from backend.api.ingestion_run_store import get_ingestion_run_store


router = APIRouter(prefix="/api/evals", tags=["eval-center"])


@router.post("/run", response_model=EvalRunResponse, status_code=status.HTTP_201_CREATED)
def run_eval(payload: EvalRunRequest) -> EvalRunResponse:
    run = build_eval_run(
        events=get_crisis_event_store().list_events(limit=100_000),
        ingestion_runs=get_ingestion_run_store().list_runs(limit=100_000),
        agent_runs=get_event_agent_run_store().list_runs(),
        requested_dimensions=payload.dimensions,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        get_eval_run_store().save(run)
    return EvalRunResponse(**run)


@router.get("/runs", response_model=EvalRunListResponse)
def list_eval_runs(limit: int = Query(default=20, ge=1, le=100)) -> EvalRunListResponse:
    runs = get_eval_run_store().list_runs(limit=limit)
    return EvalRunListResponse(runs=[_list_item(run) for run in runs], count=len(runs))


@router.get("/runs/{eval_run_id}", response_model=EvalRunResponse)
def get_eval_run(eval_run_id: str) -> EvalRunResponse:
    run = get_eval_run_store().get(eval_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Eval run '{eval_run_id}' not found.")
    return EvalRunResponse(**run)


@router.get("/overview", response_model=EvalOverviewResponse)
def get_eval_overview() -> EvalOverviewResponse:
    return EvalOverviewResponse(**build_eval_overview(get_eval_run_store().list_runs(limit=100_000)))


@router.get("/regression", response_model=EvalRegressionResponse)
def get_eval_regression() -> EvalRegressionResponse:
    return EvalRegressionResponse(**build_regression(get_eval_run_store().list_runs(limit=2)))


def _list_item(run: dict) -> EvalRunListItem:
    return EvalRunListItem(
        eval_run_id=run["eval_run_id"],
        created_at=run["created_at"],
        finished_at=run["finished_at"],
        status=run["status"],
        total_cases=run["total_cases"],
        passed_cases=run["passed_cases"],
        failed_cases=run["failed_cases"],
        pass_rate=run["pass_rate"],
        dimensions=run.get("dimensions", {}),
        automatic_publish=False,
    )
