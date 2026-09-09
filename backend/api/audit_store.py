from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_STORE_PATH = PROJECT_ROOT / "data" / "audit_logs.runtime.json"
_AUDIT_STORE_LOCK = threading.RLock()


class JsonAuditStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("AUDIT_LOG_STORE_PATH", DEFAULT_AUDIT_STORE_PATH))

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        with _AUDIT_STORE_LOCK:
            logs = self._load_logs()
            record = {"audit_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), **entry}
            logs.append(record)
            self._atomic_write(logs)
            return record

    def list_logs(self, limit: int = 50, newest_first: bool = True, **filters: str | None) -> list[dict[str, Any]]:
        with _AUDIT_STORE_LOCK:
            logs = self._load_logs()
        for key, value in filters.items():
            if value is not None:
                logs = [item for item in logs if item.get(key) == value]
        logs = logs[-limit:]
        return list(reversed(logs)) if newest_first else logs

    def _load_logs(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._quarantine_corrupt_file()
            return []
        # Older local versions stored the list directly. Keep it readable.
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        logs = payload.get("logs", [])
        return [item for item in logs if isinstance(item, dict)] if isinstance(logs, list) else []

    def _atomic_write(self, logs: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({"logs": logs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _quarantine_corrupt_file(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.path.with_name(f"{self.path.stem}.corrupt.{timestamp}{self.path.suffix}")
        try:
            os.replace(self.path, backup)
        except OSError as exc:
            raise RuntimeError(f"Audit log JSON is invalid and could not be quarantined: {self.path}") from exc


def get_audit_store() -> JsonAuditStore:
    return JsonAuditStore()
