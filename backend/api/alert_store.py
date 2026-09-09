from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALERT_PATH = ROOT / "data" / "alerts.runtime.json"


class JsonAlertStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("ALERT_STORE_PATH", DEFAULT_ALERT_PATH))

    def list(self, status=None, limit=100):
        values = self._load()
        values = [item for item in values if status is None or item.get("status") == status]
        return list(reversed(values[-limit:]))

    def create(self, entity: dict, item_ids: list[str], reason: str, severity: str) -> dict:
        value = {"alert_id": f"alert-{uuid4().hex[:12]}", "entity_id": entity["entity_id"], "entity_name": entity["entity_name"], "severity": severity, "title": f"{entity['entity_name']} public signal requires attention", "reason": reason, "related_item_ids": item_ids, "related_event_id": None, "status": "open", "created_at": datetime.now(timezone.utc).isoformat(), "acknowledged_by": None, "acknowledged_at": None}
        values = self._load()
        values.append(value)
        self._save(values)
        return value

    def ack(self, alert_id: str, actor_id: str) -> dict:
        values = self._load()
        for index, item in enumerate(values):
            if item.get("alert_id") == alert_id:
                item = {**item, "status": "acknowledged", "acknowledged_by": actor_id, "acknowledged_at": datetime.now(timezone.utc).isoformat()}
                values[index] = item
                self._save(values)
                return item
        raise KeyError(alert_id)

    def _load(self):
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload.get("alerts", []) if isinstance(payload, dict) else []

    def _save(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"alerts": values}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_alert_store():
    return JsonAlertStore()
