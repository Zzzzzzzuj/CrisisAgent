"""Run CrisisAgent's deterministic Eval Center from the command line.

This command reads local runtime stores only. It never enables live-fetch,
replays an Agent, or calls an LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.eval_service import ALL_DIMENSIONS, build_eval_run, build_regression  # noqa: E402
from backend.api.eval_store import get_eval_run_store  # noqa: E402
from backend.api.event_run_store import get_event_agent_run_store  # noqa: E402
from backend.api.event_store import get_crisis_event_store  # noqa: E402
from backend.api.ingestion_run_store import get_ingestion_run_store  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline CrisisAgent Eval CI Gate.")
    parser.add_argument(
        "--dimensions",
        help=f"Comma-separated dimensions. Defaults to: {','.join(ALL_DIMENSIONS)}",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--min-pass-rate", type=float, default=0.8, help="Fail below this pass rate (default: 0.8).")
    parser.add_argument("--fail-on-regression", action="store_true", help="Fail on a lower pass rate or newly failed cases.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def run_cli(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    dimensions = None
    if args.dimensions:
        dimensions = [item.strip() for item in args.dimensions.split(",") if item.strip()]
        invalid = sorted(set(dimensions) - set(ALL_DIMENSIONS))
        if invalid:
            return {"error": f"Unsupported eval dimensions: {', '.join(invalid)}"}, 2

    run = build_eval_run(
        events=get_crisis_event_store().list_events(limit=100_000),
        ingestion_runs=get_ingestion_run_store().list_runs(limit=100_000),
        agent_runs=get_event_agent_run_store().list_runs(),
        requested_dimensions=dimensions,
        dry_run=True,
    )
    history = get_eval_run_store().list_runs(limit=2)
    regression = build_regression([run, *history]) if history else {"not_enough_runs": True}
    pass_rate_ok = run["pass_rate"] >= args.min_pass_rate
    regression_detected = not regression.get("not_enough_runs", True) and (
        float(regression.get("delta") or 0.0) < 0 or bool(regression.get("newly_failed_cases"))
    )
    result = {
        "eval_run": run,
        "regression": regression,
        "gate": {
            "min_pass_rate": args.min_pass_rate,
            "pass_rate_ok": pass_rate_ok,
            "fail_on_regression": args.fail_on_regression,
            "regression_detected": regression_detected,
            "offline_only": True,
        },
    }
    exit_code = 0 if pass_rate_ok and (not args.fail_on_regression or not regression_detected) else 1
    return result, exit_code


def main() -> int:
    args = parse_args()
    result, exit_code = run_cli(args)
    report_content = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, default=str)
    eval_run = result.get("eval_run", {})
    console_result = {
        "eval_run_id": eval_run.get("eval_run_id"),
        "status": eval_run.get("status"),
        "total_cases": eval_run.get("total_cases"),
        "passed_cases": eval_run.get("passed_cases"),
        "failed_cases": eval_run.get("failed_cases"),
        "pass_rate": eval_run.get("pass_rate"),
        "dimensions": eval_run.get("dimensions"),
        "failed_case_ids": [item.get("case_id") for item in eval_run.get("failed_items", [])],
        "regression": result.get("regression"),
        "gate": result.get("gate"),
    }
    print(json.dumps(console_result, ensure_ascii=False, indent=2 if args.pretty else None, default=str))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_content + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
