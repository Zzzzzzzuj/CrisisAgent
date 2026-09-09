from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.api.watchlist_schemas import WatchlistCreateRequest, WatchlistUpdateRequest, ENTITY_TYPES, PRIORITIES


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WATCHLIST_PATH = ROOT / "data" / "watchlists.runtime.json"


class JsonWatchlistStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("WATCHLIST_STORE_PATH", DEFAULT_WATCHLIST_PATH))

    def list(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        values = self._load()
        return [item for item in values if enabled is None or item.get("enabled") is enabled]

    def get(self, entity_id: str) -> dict[str, Any] | None:
        return next((item for item in self._load() if item.get("entity_id") == entity_id), None)

    def create(self, payload: WatchlistCreateRequest, actor_id: str, owner_id: str) -> dict[str, Any]:
        self._validate(payload.entity_type, payload.priority)
        now = _now()
        value = {
            "entity_id": f"entity-{uuid4().hex[:12]}", "entity_name": payload.entity_name.strip(),
            "entity_type": payload.entity_type, "aliases": _clean(payload.aliases), "products": _clean(payload.products),
            "company_keywords": _clean(payload.company_keywords), "risk_keywords": _clean(payload.risk_keywords),
            "exclude_keywords": _clean(payload.exclude_keywords), "languages": _clean(payload.languages),
            "regions": _clean(payload.regions), "priority": payload.priority, "enabled": payload.enabled,
            "created_by": actor_id, "owner_id": owner_id, "created_at": now, "updated_at": now,
        }
        values = self._load()
        values.append(value)
        self._save(values)
        return value

    def update(self, entity_id: str, payload: WatchlistUpdateRequest, actor_id: str) -> dict[str, Any]:
        values = self._load()
        for index, current in enumerate(values):
            if current.get("entity_id") != entity_id:
                continue
            changes = payload.model_dump(exclude_unset=True)
            if "priority" in changes:
                self._validate(current.get("entity_type"), changes["priority"])
            for key, value in changes.items():
                current[key] = _clean(value) if isinstance(value, list) else value
            current["updated_at"] = _now()
            current["updated_by"] = actor_id
            values[index] = current
            self._save(values)
            return current
        raise KeyError(entity_id)

    def archive(self, entity_id: str, actor_id: str) -> dict[str, Any]:
        return self.update(entity_id, WatchlistUpdateRequest(enabled=False), actor_id)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload.get("watchlists", []) if isinstance(payload, dict) else []

    def _save(self, values: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"watchlists": values}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _validate(entity_type: str, priority: str) -> None:
        if entity_type not in ENTITY_TYPES:
            raise ValueError("entity_type must be company, brand, product, person, or organization")
        if priority not in PRIORITIES:
            raise ValueError("priority must be low, medium, or high")


def get_watchlist_store() -> JsonWatchlistStore:
    return JsonWatchlistStore()


def _clean(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
