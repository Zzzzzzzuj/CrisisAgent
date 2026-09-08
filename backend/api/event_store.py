from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENT_STORE_PATH = PROJECT_ROOT / "data" / "crisis_events.runtime.json"
ALLOWED_EVENT_STATUSES = {
    "new", "ready_for_agent", "running", "waiting_human",
    "completed", "failed", "rejected", "archived",
}


class JsonCrisisEventStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("CRISIS_EVENT_STORE_PATH", DEFAULT_EVENT_STORE_PATH))

    def list_events(
        self,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        events = self._load()
        if status is not None:
            events = [event for event in events if event.get("status") == status]
        if risk_level is not None:
            events = [event for event in events if event.get("risk_level") == risk_level]
        return list(reversed(events[-limit:]))

    def get(self, event_id: str) -> dict[str, Any] | None:
        return next((event for event in self._load() if event.get("event_id") == event_id), None)

    def find_by_source(self, source_run_id: str, cluster_id: str) -> dict[str, Any] | None:
        return next(
            (
                event
                for event in self._load()
                if event.get("source_run_id") == source_run_id
                and event.get("cluster_id") == cluster_id
            ),
            None,
        )

    def create_from_cluster(
        self,
        *,
        source_run_id: str,
        cluster: dict[str, Any],
        title: str | None = None,
        event_summary: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        cluster_id = str(cluster.get("cluster_id", ""))
        existing = self.find_by_source(source_run_id, cluster_id)
        if existing is not None:
            return existing, False

        now = _now()
        event = {
            "event_id": str(uuid4()),
            "cluster_id": cluster_id,
            "source_run_id": source_run_id,
            "title": title or _default_title(cluster),
            "event_summary": event_summary or str(cluster.get("event", "")),
            "company": str(cluster.get("company", "")),
            "risk_level": str(cluster.get("risk_level", "")),
            "public_emotion": str(cluster.get("public_emotion", "")),
            "fact_status": str(cluster.get("fact_status", "")),
            "event_status": str(cluster.get("event_status", "")),
            "human_review_required": bool(cluster.get("human_review_required", False)),
            "source_count": int(cluster.get("source_count", 0)),
            "source_items": [str(item) for item in cluster.get("source_items", [])],
            "first_published_at": str(cluster.get("first_published_at", "")),
            "last_published_at": str(cluster.get("last_published_at", "")),
            "event_fingerprint": str(cluster.get("event_fingerprint", "")),
            "status": "new",
            "created_at": now,
            "updated_at": now,
            "created_by": str((actor or {}).get("id", "demo-system")),
            "updated_by": str((actor or {}).get("id", "demo-system")),
            "owner_id": str((actor or {}).get("id", "demo-system")),
        }
        events = self._load()
        events.append(event)
        self._save(events)
        return event, True

    def update(self, event_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        events = self._load()
        for index, event in enumerate(events):
            if event.get("event_id") != event_id:
                continue
            if "status" in changes and changes["status"] not in ALLOWED_EVENT_STATUSES:
                raise ValueError(f"Unsupported event status: {changes['status']}")
            event.update({key: value for key, value in changes.items() if value is not None})
            event["updated_at"] = _now()
            events[index] = event
            self._save(events)
            return event
        return None

    def archive(self, event_id: str) -> dict[str, Any] | None:
        return self.update(event_id, {"status": "archived"})

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("Crisis event store must contain an events array.")
        return [item for item in payload["events"] if isinstance(item, dict)]

    def _save(self, events: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"events": events}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def get_crisis_event_store() -> JsonCrisisEventStore:
    return JsonCrisisEventStore()


def _default_title(cluster: dict[str, Any]) -> str:
    event = str(cluster.get("event", "")).strip()
    company = str(cluster.get("company", "")).strip()
    if event:
        return event[:80]
    return company or "未命名危机事件"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
