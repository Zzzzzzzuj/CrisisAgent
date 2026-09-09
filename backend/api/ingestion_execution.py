from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import os
from typing import Any

from fastapi import HTTPException

from backend.api.source_routes import get_source_store
from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.source_adapters import FetchResult, HttpArticleSourceAdapter, RssSourceAdapter
from backend.ingestion.source_registry import SourceDefinition


def validate_ingestion_payload(payload: dict[str, Any]) -> list[SourceDefinition]:
    """Validate source selection and the live-fetch guard before execution."""
    live_fetch = bool(payload.get("live_fetch", False))
    dry_run = bool(payload.get("dry_run", False))
    if live_fetch and not dry_run and not api_live_fetch_enabled():
        raise HTTPException(
            status_code=403,
            detail="live fetch is disabled by server config; set ENABLE_API_LIVE_FETCH=true to enable it.",
        )
    try:
        sources = select_sources(payload.get("source_ids"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Source '{exc.args[0]}' not found.") from exc
    if not sources:
        raise HTTPException(status_code=400, detail="No sources selected for ingestion.")

    max_items_override = payload.get("max_items_override")
    for source in sources:
        if max_items_override is not None and max_items_override > source.max_items:
            raise HTTPException(
                status_code=422,
                detail=f"max_items_override cannot exceed source '{source.source_id}' max_items.",
            )
    return sources


def execute_ingestion_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the existing source adapters and ingestion pipeline once.

    This module owns no queue state. Both the synchronous route and RQ worker
    call it so normalization, deduplication, clustering, and risk analysis stay
    on exactly one implementation path.
    """
    sources = validate_ingestion_payload(payload)
    live_fetch = bool(payload.get("live_fetch", False))
    dry_run = bool(payload.get("dry_run", False))
    max_items_override = payload.get("max_items_override")
    started_at = now()
    source_results: list[dict[str, Any]] = []
    raw_items = []

    if live_fetch and not dry_run:
        for source in sources:
            effective_source = replace(source, max_items=max_items_override) if max_items_override is not None else source
            result = fetch_source(effective_source)
            source_results.append(fetch_result_dict(result))
            raw_items.extend(result.items)
    else:
        # Non-live and dry runs intentionally never invoke a network adapter.
        for source in sources:
            source_results.append(
                {
                    "source_id": source.source_id,
                    "source_name": source.source_name,
                    "status": "disabled",
                    "fetched_count": 0,
                    "matched_count": 0,
                    "failed_reason": "dry_run" if dry_run else "live_fetch_disabled",
                    "items": [],
                }
            )

    clusters = run_sentiment_ingestion_items(raw_items) if raw_items else []
    failed_count = sum(1 for item in source_results if item["status"] in {"failed", "skipped_by_robots"})
    return {
        "status": "dry_run" if dry_run else run_status(live_fetch, source_results, failed_count),
        "live_fetch": live_fetch,
        "started_at": started_at,
        "finished_at": now(),
        "source_results": source_results,
        "raw_count": len(raw_items),
        "deduped_count": len({item_id for cluster in clusters for item_id in cluster.source_items}),
        "cluster_count": len(clusters),
        "clusters": [asdict(cluster) for cluster in clusters],
        "automatic_publish": False,
        "dry_run": dry_run,
        "error": None,
    }


def select_sources(source_ids: list[str] | None) -> list[SourceDefinition]:
    store = get_source_store()
    if source_ids is None:
        return [SourceDefinition(**item) for item in store.list_sources()]
    return [store.get(source_id) for source_id in source_ids]


def fetch_source(source: SourceDefinition) -> FetchResult:
    if source.source_type == "rss":
        return RssSourceAdapter().fetch(source)
    if source.source_type == "article_url":
        return HttpArticleSourceAdapter().fetch(source)
    raise ValueError(f"Unsupported source_type: {source.source_type}")


def fetch_result_dict(result: FetchResult) -> dict[str, Any]:
    return {
        "source_id": result.source_id,
        "source_name": result.source_name,
        "status": result.status,
        "fetched_count": result.fetched_count,
        "matched_count": result.matched_count,
        "failed_reason": result.failed_reason,
        "items": [asdict(item) for item in result.items],
    }


def run_status(live_fetch: bool, source_results: list[dict[str, Any]], failed_count: int) -> str:
    if not live_fetch:
        return "completed"
    if failed_count == len(source_results):
        return "failed"
    if failed_count:
        return "partial"
    return "completed"


def api_live_fetch_enabled() -> bool:
    return os.getenv("ENABLE_API_LIVE_FETCH", "false").strip().lower() == "true"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
