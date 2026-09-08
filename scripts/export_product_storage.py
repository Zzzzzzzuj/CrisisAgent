from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.audit_store import get_audit_store
from backend.api.eval_store import get_eval_run_store
from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_store import get_crisis_event_store
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.source_routes import get_source_store


def export_payload() -> dict:
    return {
        "sources": get_source_store().list_sources(),
        "ingestion_runs": get_ingestion_run_store().list_runs(limit=100_000),
        "crisis_events": get_crisis_event_store().list_events(limit=100_000),
        "event_agent_runs": get_event_agent_run_store().list_runs(),
        "eval_runs": get_eval_run_store().list_runs(limit=100_000),
        "audit_logs": get_audit_store().list_logs(limit=100_000),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export JSON product stores without connecting to a database.")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "product_storage_export.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(export_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
