from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dashboard_schemas import (
    DashboardOverviewResponse,
    DashboardReviewQueueResponse,
    DashboardSeverityResponse,
    DashboardSourceHealthResponse,
    DashboardTrendsResponse,
)
from backend.api.dashboard_service import (
    build_overview,
    build_review_queue,
    build_severity_groups,
    build_source_health,
    build_trends,
)
from backend.api.event_store import get_crisis_event_store
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.workspace_security import authorize, get_workspace_user, write_audit


router = APIRouter(prefix="/api/dashboard", tags=["crisis-radar"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(user: dict = Depends(get_workspace_user)) -> DashboardOverviewResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "dashboard.view", "dashboard", "overview")
    write_audit(user, "dashboard.view", "dashboard", "overview")
    return DashboardOverviewResponse(**build_overview(_all_events()))


@router.get("/severity", response_model=DashboardSeverityResponse)
def get_dashboard_severity(user: dict = Depends(get_workspace_user)) -> DashboardSeverityResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "dashboard.view", "dashboard", "severity")
    return DashboardSeverityResponse(groups=build_severity_groups(_all_events()))


@router.get("/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends(user: dict = Depends(get_workspace_user)) -> DashboardTrendsResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "dashboard.view", "dashboard", "trends")
    return DashboardTrendsResponse(buckets=build_trends(_all_events()))


@router.get("/source-health", response_model=DashboardSourceHealthResponse)
def get_dashboard_source_health(user: dict = Depends(get_workspace_user)) -> DashboardSourceHealthResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "dashboard.view", "dashboard", "source_health")
    sources = build_source_health(get_ingestion_run_store().list_runs(limit=100_000))
    return DashboardSourceHealthResponse(sources=sources, count=len(sources))


@router.get("/review-queue", response_model=DashboardReviewQueueResponse)
def get_dashboard_review_queue(user: dict = Depends(get_workspace_user)) -> DashboardReviewQueueResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "dashboard.view", "dashboard", "review_queue")
    events = build_review_queue(_all_events())
    return DashboardReviewQueueResponse(events=events, count=len(events))


def _all_events() -> list[dict]:
    # Event store's default list limit is presentation-oriented; Radar needs all rows.
    return get_crisis_event_store().list_events(limit=100_000)
