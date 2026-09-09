from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.ingestion_recovery import recover_stuck_runs
from backend.api.ingestion_queue import IngestionQueueUnavailable


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover stale queued or running ingestion runs.")
    parser.add_argument("--max-age-seconds", type=int, default=600)
    parser.add_argument("--mode", choices=["mark-failed", "requeue"], default="mark-failed")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true", help="Apply changes instead of the safe default dry-run.")
    args = parser.parse_args()
    try:
        affected = recover_stuck_runs(args.max_age_seconds, args.mode, dry_run=not args.apply)
    except IngestionQueueUnavailable as exc:
        print(f"Recovery failed: {exc}", file=sys.stderr)
        return 2
    print({"dry_run": not args.apply, "mode": args.mode, "affected_run_ids": affected})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
