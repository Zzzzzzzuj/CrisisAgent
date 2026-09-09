from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

from backend.api.ingestion_queue import IngestionQueueUnavailable, get_redis_connection


def current_worker_id() -> str:
    return os.getenv("INGESTION_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"


def update_worker_heartbeat(worker_id: str, queue_name: str, status: str, connection=None) -> dict[str, Any]:
    connection = connection or get_redis_connection()
    now = datetime.now(timezone.utc).isoformat()
    key = f"worker:ingestion:{worker_id}:heartbeat"
    existing = _read_heartbeat(connection, key) or {}
    payload = {"worker_id": worker_id, "queue_name": queue_name, "started_at": existing.get("started_at", now), "last_seen_at": now, "status": status}
    connection.setex(key, 120, json.dumps(payload))
    return payload


def list_worker_heartbeats(connection=None) -> list[dict[str, Any]]:
    connection = connection or get_redis_connection()
    results = []
    for raw_key in connection.scan_iter(match="worker:ingestion:*:heartbeat"):
        key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        heartbeat = _read_heartbeat(connection, key)
        if heartbeat:
            results.append(heartbeat)
    return sorted(results, key=lambda item: item.get("last_seen_at", ""), reverse=True)


def _read_heartbeat(connection, key: str) -> dict[str, Any] | None:
    raw = connection.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, json.JSONDecodeError):
        return None
