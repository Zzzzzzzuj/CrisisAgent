from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
from typing import Any
from uuid import uuid4

from backend.api.alert_store import get_alert_store
from backend.api.collected_item_store import get_collected_item_store
from backend.api.ingestion_execution import fetch_source, now
from backend.api.source_routes import get_source_store
from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.query_builder import build_monitor_query
from backend.api.watchlist_store import get_watchlist_store


def execute_monitor_payload(payload: dict[str, Any], monitor_run_id: str) -> dict[str, Any]:
    entities = _select_entities(payload.get("entity_ids"))
    providers = payload.get("providers") or ["gdelt_doc", "news_api", "rss"]
    max_items = int(payload.get("max_items_per_entity", 10))
    live_fetch = bool(payload.get("live_fetch", False))
    raw_items = []
    source_results = []
    collected = []
    alerts = []
    for entity in entities:
        for provider in providers:
            query = build_monitor_query(entity, provider, int(payload.get("lookback_minutes", 60)), max_items)
            source = _provider_source(provider)
            if source is None:
                source_results.append(_result(entity, provider, "failed", "provider_not_configured"))
                continue
            effective = replace(source, query=query.query, language=query.language, max_items=min(source.max_items, query.max_items), company_keywords=tuple(_names(entity)), risk_keywords=tuple(entity.get("risk_keywords") or []))
            if not live_fetch:
                source_results.append(_result(entity, provider, "disabled", "live_fetch_disabled"))
                continue
            result = fetch_source(effective)
            source_results.append({**asdict_result(result), "entity_id": entity["entity_id"], "provider": provider})
            raw_items.extend(result.items)
            for item in result.items:
                record = _collected_record(item, entity, provider, monitor_run_id, result)
                collected.append(record)
            if result.status == "collected" and result.items and (result.matched_count > 0):
                risk_matches = [key for key in entity.get("risk_keywords", []) if any(key.lower() in f"{item.title} {item.content}".lower() for item in result.items)]
                if risk_matches:
                    severity = "SEV-2" if entity.get("priority") == "high" else "SEV-3"
                    alert = get_alert_store().create(entity, [record["item_id"] for record in collected if record["entity_id"] == entity["entity_id"]], f"risk_keywords_matched:{','.join(risk_matches)}", severity)
                    alerts.append(alert)
    clusters = run_sentiment_ingestion_items(raw_items) if raw_items else []
    if collected:
        get_collected_item_store().save_many(collected)
    failed = sum(1 for item in source_results if item.get("status") in {"failed", "skipped_by_robots"})
    status = "failed" if source_results and failed == len(source_results) else "partial" if failed else "completed"
    return {"monitor_run_id": monitor_run_id, "status": status, "live_fetch": live_fetch, "background": bool(payload.get("background", False)), "entity_count": len(entities), "provider_count": len(providers), "source_results": source_results, "item_count": len(collected), "cluster_count": len(clusters), "clusters": [asdict(cluster) for cluster in clusters], "alert_count": len(alerts), "automatic_publish": False, "error": None}


def _select_entities(entity_ids):
    values = get_watchlist_store().list(enabled=True)
    if entity_ids is None:
        return values
    requested = set(entity_ids)
    return [item for item in values if item.get("entity_id") in requested]


def _provider_source(provider):
    for item in get_source_store().list_sources():
        if item.get("source_type") == provider and item.get("enabled") is True:
            from backend.ingestion.source_registry import SourceDefinition
            return SourceDefinition(**item)
    return None


def _names(entity):
    return [entity.get("entity_name", ""), *(entity.get("aliases") or []), *(entity.get("products") or []), *(entity.get("company_keywords") or [])]


def _result(entity, provider, status, reason):
    return {"source_id": None, "source_name": provider, "status": status, "fetched_count": 0, "matched_count": 0, "failed_reason": reason, "adapter_type": provider, "entity_id": entity["entity_id"], "provider": provider, "items": []}


def asdict_result(result):
    return {"source_id": result.source_id, "source_name": result.source_name, "status": result.status, "fetched_count": result.fetched_count, "matched_count": result.matched_count, "failed_reason": result.failed_reason, "adapter_type": result.adapter_type, "duration_ms": result.duration_ms, "error_type": result.error_type, "robots_allowed": result.robots_allowed, "items": [asdict(item) for item in result.items]}


def _collected_record(item, entity, provider, run_id, result):
    content_hash = sha256(f"{item.source_url}|{item.title}|{item.content}".encode("utf-8")).hexdigest()
    text = f"{item.title} {item.content}".lower()
    risks = [key for key in entity.get("risk_keywords", []) if key.lower() in text]
    return {"item_id": str(uuid4()), "source_id": result.source_id, "source_name": result.source_name, "source_type": provider, "ingestion_run_id": run_id, "entity_id": entity["entity_id"], "entity_name": entity["entity_name"], "provider": provider, "title": item.title[:500], "url": item.source_url, "summary": item.content[:500], "content_preview": item.content[:2000], "published_at": item.published_at, "collected_at": now(), "matched_company_keywords": entity.get("company_keywords", []), "matched_risk_keywords": risks, "content_hash": content_hash, "status": "collected", "reason": None, "relevance_score": 1.0, "risk_score": min(1.0, len(risks) / 3), "sentiment_hint": "negative" if risks else "unknown", "metadata": {"monitor_run_id": run_id, "adapter_type": result.adapter_type}}
