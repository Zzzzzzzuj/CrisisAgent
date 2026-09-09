from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import os
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend.api.source_routes import get_source_store
from backend.api.collected_item_store import get_collected_item_store
from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.source_adapters import FetchResult, GdeltDocSourceAdapter, HttpArticleSourceAdapter, NewsApiSourceAdapter, RssSourceAdapter
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


def execute_ingestion_payload(payload: dict[str, Any], *, ingestion_run_id: str | None = None) -> dict[str, Any]:
    """Run the existing source adapters and ingestion pipeline once.

    This module owns no queue state. Both the synchronous route and RQ worker
    call it so normalization, deduplication, clustering, and risk analysis stay
    on exactly one implementation path.
    """
    # Workers carry the durable run identity in internal payload context so
    # legacy one-argument call sites and test doubles remain compatible.
    ingestion_run_id = ingestion_run_id or payload.get("_ingestion_run_id")
    sources = validate_ingestion_payload(payload)
    live_fetch = bool(payload.get("live_fetch", False))
    dry_run = bool(payload.get("dry_run", False))
    max_items_override = payload.get("max_items_override")
    started_at = now()
    source_results: list[dict[str, Any]] = []
    raw_items = []
    collected_items: list[dict[str, Any]] = []

    if live_fetch and not dry_run:
        for source in sources:
            effective_source = replace(source, max_items=max_items_override) if max_items_override is not None else source
            result = fetch_source(effective_source)
            source_results.append(fetch_result_dict(result))
            raw_items.extend(result.items)
            if ingestion_run_id and result.status == "collected":
                collected_items.extend(_collected_records(ingestion_run_id, effective_source, result))
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
    if collected_items:
        get_collected_item_store().save_many(collected_items)
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
    if source.source_type == "gdelt_doc":
        return GdeltDocSourceAdapter().fetch(source)
    if source.source_type == "news_api":
        return NewsApiSourceAdapter().fetch(source)
    raise ValueError(f"Unsupported source_type: {source.source_type}")


def fetch_result_dict(result: FetchResult) -> dict[str, Any]:
    return {
        "source_id": result.source_id,
        "source_name": result.source_name,
        "status": result.status,
        "fetched_count": result.fetched_count,
        "matched_count": result.matched_count,
        "failed_reason": result.failed_reason,
        "adapter_type": result.adapter_type,
        "duration_ms": result.duration_ms,
        "error_type": result.error_type,
        "robots_allowed": result.robots_allowed,
        "items": [asdict(item) for item in result.items],
    }


def _collected_records(ingestion_run_id: str, source: SourceDefinition, result: FetchResult) -> list[dict[str, Any]]:
    collected_at = now()
    records = []
    for item in result.items:
        content_hash = sha256(f"{item.source_url}|{item.title}|{item.content}".encode("utf-8")).hexdigest()
        companies, risks = source.matched_keywords(f"{item.title} {item.content}")
        records.append(
            {
                "item_id": str(uuid4()), "source_id": source.source_id, "source_name": source.source_name,
                "source_type": source.source_type, "ingestion_run_id": ingestion_run_id,
                "title": item.title[:500], "url": item.source_url, "summary": item.content[:500],
                "content_preview": item.content[:2000], "published_at": item.published_at,
                "collected_at": collected_at, "matched_company_keywords": companies,
                "matched_risk_keywords": risks, "content_hash": content_hash, "status": "collected",
                "reason": None, "metadata": {"adapter_type": result.adapter_type, "duration_ms": result.duration_ms, **(item.metadata or {})},
            }
        )
    return records


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
