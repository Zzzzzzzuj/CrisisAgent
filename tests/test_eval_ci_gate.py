from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from backend.api.eval_service import build_eval_run, build_regression, evaluate_golden_cases, load_golden_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_golden_cases_load_and_validate_offline():
    cases = load_golden_cases()
    items, summary = evaluate_golden_cases(cases)

    assert len(cases) >= 8
    assert summary["golden_case_count"] == len(cases)
    assert summary["golden_case_pass_rate"] == 1.0
    assert all(item["passed"] for item in items)


def test_high_risk_and_historical_golden_rules_are_enforced():
    cases = load_golden_cases()
    high_risk = next(case.copy() for case in cases if case["expected_risk_level"] == "high")
    high_risk["expected_human_review_required"] = False
    historical = next(case.copy() for case in cases if case["expected_event_status"] == "historical")
    historical["expected_min_severity"] = "SEV-1"

    items, _ = evaluate_golden_cases([high_risk, historical])
    failed = {item["case_id"] for item in items if not item["passed"]}
    assert f"golden_case.{high_risk['case_id']}.high_risk_review" in failed
    assert f"golden_case.{historical['case_id']}.historical_not_sev1" in failed


def test_golden_dimension_is_available_in_eval_run():
    run = build_eval_run(events=[], ingestion_runs=[], agent_runs=[], requested_dimensions=["golden_case"], dry_run=True)
    assert set(run["dimensions"]) == {"golden_case"}
    assert run["dimensions"]["golden_case"]["golden_case_count"] >= 8
    assert run["pass_rate"] == 1.0


def test_cli_writes_report_and_enforces_minimum_pass_rate(tmp_path):
    output = tmp_path / "eval_report.json"
    env = _offline_env(tmp_path)
    command = [sys.executable, "scripts/run_eval_center.py", "--dimensions", "golden_case", "--output", str(output), "--min-pass-rate", "0.8"]
    success = subprocess.run(command, cwd=PROJECT_ROOT, env=env, text=True, capture_output=True, check=False)

    assert success.returncode == 0, success.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["eval_run"]["dimensions"]["golden_case"]["pass_rate"] == 1.0
    assert report["gate"]["offline_only"] is True

    failing = subprocess.run(
        [sys.executable, "scripts/run_eval_center.py", "--dimensions", "golden_case", "--min-pass-rate", "1.01"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert failing.returncode == 1


def test_regression_needs_history_then_calculates_delta():
    current = build_eval_run(events=[], ingestion_runs=[], agent_runs=[], requested_dimensions=["golden_case"], dry_run=True)
    assert build_regression([current])["not_enough_runs"] is True

    previous = {**current, "eval_run_id": "previous", "pass_rate": 0.8, "failed_items": [{"case_id": "old_failure"}]}
    current = {**current, "eval_run_id": "current", "pass_rate": 1.0, "failed_items": []}
    regression = build_regression([current, previous])
    assert regression["not_enough_runs"] is False
    assert regression["delta"] == 0.2
    assert regression["recovered_cases"] == ["old_failure"]


def _offline_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENT_MODE": "mock",
            "CHECKPOINT_STORAGE": "json",
            "RUNTIME_MODE": "sync",
            "TASK_QUEUE_BACKEND": "inprocess",
            "EMBEDDING_MODEL": "hash",
            "VECTOR_BACKEND": "json",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "EVAL_RUN_STORE_PATH": str(tmp_path / "eval_runs.json"),
            "CRISIS_EVENT_STORE_PATH": str(tmp_path / "events.json"),
            "INGESTION_RUN_STORE_PATH": str(tmp_path / "ingestion.json"),
            "EVENT_AGENT_RUN_STORE_PATH": str(tmp_path / "agent_runs.json"),
        }
    )
    return env
