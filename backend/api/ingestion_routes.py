from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.ingestion_schemas import (
    IngestionRunListResponse,
    IngestionRunRequest,
    IngestionRunResponse,
    IngestionRunSummary,
)
from backend.api.source_routes import get_source_store
from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.source_adapters import HttpArticleSourceAdapter, RssSourceAdapter, FetchResult
from backend.ingestion.source_registry import SourceDefinition


router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.post("/run", response_model=IngestionRunResponse, status_code=status.HTTP_201_CREATED)
def run_ingestion(payload: IngestionRunRequest) -> IngestionRunResponse:
    if payload.live_fetch and not payload.dry_run and not _api_live_fetch_enabled():
        raise HTTPException(
            status_code=403,
            detail="live fetch is disabled by server config; set ENABLE_API_LIVE_FETCH=true to enable it.",
        )
    try:
        sources = _select_sources(payload.source_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Source '{exc.args[0]}' not found.") from exc
    if not sources:
        raise HTTPException(status_code=400, detail="No sources selected for ingestion.")

    for source in sources:
        if payload.max_items_override is not None and payload.max_items_override > source.max_items:
            raise HTTPException(
                status_code=422,
                detail=f"max_items_override cannot exceed source '{source.source_id}' max_items.",
            )

    started_at = _now()
    source_results: list[dict[str, Any]] = []
    raw_items = []
    if payload.live_fetch and not payload.dry_run:
        for source in sources:
            effective_source = (
                replace(source, max_items=payload.max_items_override)
                if payload.max_items_override is not None
                else source
            )
            result = _fetch_source(effective_source)
            source_results.append(_fetch_result_dict(result))
            raw_items.extend(result.items)
    else:
        # A non-live run is an explicit configuration-only execution. It never
        # calls an adapter and therefore cannot access the network.
        for source in sources:
            source_results.append(
                {
                    "source_id": source.source_id,
                    "source_name": source.source_name,
                    "status": "disabled",
                    "fetched_count": 0,
                    "matched_count": 0,
                    "failed_reason": "dry_run" if payload.dry_run else "live_fetch_disabled",
                    "items": [],
                }
            )

    clusters = run_sentiment_ingestion_items(raw_items) if raw_items else []
    finished_at = _now()
    failed_count = sum(
        1 for item in source_results if item["status"] in {"failed", "skipped_by_robots"}
    )
    run_status = _run_status(payload.live_fetch, source_results, failed_count)
    run = {
        "run_id": str(uuid4()),
        "status": "dry_run" if payload.dry_run else run_status,
        "live_fetch": payload.live_fetch,
        "started_at": started_at,
        "finished_at": finished_at,
        "source_results": source_results,
        "raw_count": len(raw_items),
        "deduped_count": len({item_id for cluster in clusters for item_id in cluster.source_items}),
        "cluster_count": len(clusters),
        "clusters": [asdict(cluster) for cluster in clusters],
        "automatic_publish": False,
        "dry_run": payload.dry_run,
    }
    if not payload.dry_run:
        get_ingestion_run_store().save(run)
    return IngestionRunResponse(**run)


@router.get("/runs", response_model=IngestionRunListResponse)
def list_ingestion_runs(limit: int = Query(default=20, ge=1, le=100)) -> IngestionRunListResponse:
    runs = get_ingestion_run_store().list_runs(limit)
    summaries = [_summary(run) for run in runs]
    return IngestionRunListResponse(runs=summaries, count=len(summaries))


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
def get_ingestion_run(run_id: str) -> IngestionRunResponse:
    run = get_ingestion_run_store().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Ingestion run '{run_id}' not found.")
    return IngestionRunResponse(**run)


def _select_sources(source_ids: list[str] | None) -> list[SourceDefinition]:
    store = get_source_store()
    if source_ids is None:
        return [SourceDefinition(**item) for item in store.list_sources()]
    selected = []
    for source_id in source_ids:
        item = store.get(source_id)
        selected.append(item)
    return selected


def _fetch_source(source: SourceDefinition) -> FetchResult:
    if source.source_type == "rss":
        return RssSourceAdapter().fetch(source)
    if source.source_type == "article_url":
        return HttpArticleSourceAdapter().fetch(source)
    raise ValueError(f"Unsupported source_type: {source.source_type}")


def _fetch_result_dict(result: FetchResult) -> dict[str, Any]:
    return {
        "source_id": result.source_id,
        "source_name": result.source_name,
        "status": result.status,
        "fetched_count": result.fetched_count,
        "matched_count": result.matched_count,
        "failed_reason": result.failed_reason,
        "items": [asdict(item) for item in result.items],
    }


def _run_status(live_fetch: bool, source_results: list[dict[str, Any]], failed_count: int) -> str:
    if not live_fetch:
        return "completed"
    if failed_count == len(source_results):
        return "failed"
    if failed_count:
        return "partial"
    return "completed"


def _summary(run: dict[str, Any]) -> IngestionRunSummary:
    source_results = run.get("source_results", [])
    return IngestionRunSummary(
        run_id=run["run_id"],
        status=run["status"],
        live_fetch=run["live_fetch"],
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        source_count=len(source_results),
        raw_count=run.get("raw_count", 0),
        deduped_count=run.get("deduped_count", 0),
        cluster_count=run.get("cluster_count", 0),
        failed_source_count=sum(
            1 for item in source_results if item.get("status") in {"failed", "skipped_by_robots"}
        ),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_live_fetch_enabled() -> bool:
    return os.getenv("ENABLE_API_LIVE_FETCH", "false").strip().lower() == "true"
