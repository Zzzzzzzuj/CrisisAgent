from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.harness.json_store import load_json_object, path_lock, save_json_object

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "harness_proposals.runtime.json"


class JsonHarnessProposalStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("HARNESS_PROPOSAL_STORE_PATH", DEFAULT_PATH))

    def list(self) -> list[dict[str, Any]]:
        with path_lock(self.path):
            return load_json_object(self.path, "proposals")

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list() if item.get("proposal_id") == proposal_id), None)

    def save(self, proposal: dict[str, Any]) -> dict[str, Any]:
        with path_lock(self.path):
            values = load_json_object(self.path, "proposals")
            values.append(proposal)
            save_json_object(self.path, "proposals", values)
        return proposal

    def replace(self, proposal: dict[str, Any]) -> dict[str, Any]:
        with path_lock(self.path):
            values = load_json_object(self.path, "proposals")
            for index, item in enumerate(values):
                if item.get("proposal_id") == proposal.get("proposal_id"):
                    values[index] = proposal
                    save_json_object(self.path, "proposals", values)
                    return proposal
        raise KeyError(f"Proposal not found: {proposal.get('proposal_id')}")


def get_harness_proposal_store() -> JsonHarnessProposalStore:
    return JsonHarnessProposalStore()
