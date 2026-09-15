from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.harness.json_store import load_json_object, path_lock, save_json_object


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HARNESS_STORE_PATH = PROJECT_ROOT / "data" / "harness_specs.runtime.json"


class JsonHarnessRepository:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("HARNESS_SPEC_STORE_PATH", DEFAULT_HARNESS_STORE_PATH))

    def list_specs(self) -> list[dict[str, Any]]:
        with path_lock(self.path):
            return self._load()

    def save(self, spec: dict[str, Any]) -> dict[str, Any]:
        with path_lock(self.path):
            specs = self._load()
            specs.append(spec)
            self._save(specs)
        return spec

    def replace(self, specs: list[dict[str, Any]]) -> None:
        with path_lock(self.path):
            self._save(specs)

    def _load(self) -> list[dict[str, Any]]:
        return load_json_object(self.path, "specs")

    def _save(self, specs: list[dict[str, Any]]) -> None:
        save_json_object(self.path, "specs", specs)


def get_harness_repository() -> JsonHarnessRepository:
    return JsonHarnessRepository()
