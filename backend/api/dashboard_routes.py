from __future__ import annotations

from fastapi import APIRouter

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


router = APIRouter(prefix="/api/dashboard", tags=["crisis-radar"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview() -> DashboardOverviewResponse:
    return DashboardOverviewResponse(**build_overview(_all_events()))


@router.get("/severity", response_model=DashboardSeverityResponse)
def get_dashboard_severity() -> DashboardSeverityResponse:
    return DashboardSeverityResponse(groups=build_severity_groups(_all_events()))


@router.get("/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends() -> DashboardTrendsResponse:
    return DashboardTrendsResponse(buckets=build_trends(_all_events()))


@router.get("/source-health", response_model=DashboardSourceHealthResponse)
def get_dashboard_source_health() -> DashboardSourceHealthResponse:
    sources = build_source_health(get_ingestion_run_store().list_runs(limit=100_000))
    return DashboardSourceHealthResponse(sources=sources, count=len(sources))


@router.get("/review-queue", response_model=DashboardReviewQueueResponse)
def get_dashboard_review_queue() -> DashboardReviewQueueResponse:
    events = build_review_queue(_all_events())
    return DashboardReviewQueueResponse(events=events, count=len(events))


def _all_events() -> list[dict]:
    # Event store's default list limit is presentation-oriented; Radar needs all rows.
    return get_crisis_event_store().list_events(limit=100_000)
