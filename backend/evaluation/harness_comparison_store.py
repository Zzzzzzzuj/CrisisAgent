from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.harness.json_store import load_json_object, path_lock, save_json_object


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "harness_comparisons.runtime.json"


class JsonHarnessComparisonStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("HARNESS_COMPARISON_STORE_PATH", DEFAULT_PATH))

    def save(self, comparison: dict[str, Any]) -> dict[str, Any]:
        with path_lock(self.path):
            values = load_json_object(self.path, "comparisons")
            values.append(comparison)
            save_json_object(self.path, "comparisons", values)
        return comparison

    def list(self) -> list[dict[str, Any]]:
        return list(reversed(self._load()))

    def get(self, comparison_id: str) -> dict[str, Any] | None:
        return next((item for item in self._load() if item.get("comparison_id") == comparison_id), None)

    def _load(self) -> list[dict[str, Any]]:
        return load_json_object(self.path, "comparisons")


def get_harness_comparison_store() -> JsonHarnessComparisonStore:
    return JsonHarnessComparisonStore()
