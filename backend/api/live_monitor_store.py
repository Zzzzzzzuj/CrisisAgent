from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MONITOR_RUN_PATH = ROOT / "data" / "live_monitor_runs.runtime.json"


class JsonLiveMonitorRunStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("LIVE_MONITOR_RUN_STORE_PATH", DEFAULT_MONITOR_RUN_PATH))

    def save(self, value: dict) -> dict:
        values = self._load()
        values.append(value)
        self._save(values)
        return value

    def list(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._load()[-limit:]))

    def get(self, run_id: str) -> dict | None:
        return next((item for item in self._load() if item.get("monitor_run_id") == run_id), None)

    def update(self, run_id: str, changes: dict) -> dict:
        values = self._load()
        for index, item in enumerate(values):
            if item.get("monitor_run_id") == run_id:
                values[index] = {**item, **changes}
                self._save(values)
                return values[index]
        raise KeyError(run_id)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload.get("runs", []) if isinstance(payload, dict) else []

    def _save(self, values: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"runs": values}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_live_monitor_run_store() -> JsonLiveMonitorRunStore:
    return JsonLiveMonitorRunStore()
