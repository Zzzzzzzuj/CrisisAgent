import argparse
import json
import pytest

from scripts import run_reliability_test as runner


def _success_run(index: int, event: str, mode: str, request_timeout: int) -> dict:
    return {
        "run_index": index,
        "session_id": f"session-{index}",
        "started_at": "2026-08-06T00:00:00+00:00",
        "ended_at": "2026-08-06T00:00:01+00:00",
        "duration_ms": 1000,
        "status": "success",
        "all_agents_success": True,
        "evaluation_passed": True,
        "failed_agents": [],
        "error": None,
        "executed_agents": list(runner.EXPECTED_AGENTS),
        "human_gate_status": "not_applicable",
        "final_statement": "safe final statement",
        "decision_scores": {
            "legal_safety": 8,
            "empathy": 8,
            "robustness": 8,
        },
        "evaluation_scores": {
            "legal_safety_score": 8,
            "empathy_score": 8,
            "robustness_score": 8,
        },
        "recommendation": "publish",
        "evaluation_result": {"passed": True},
    }


def _mixed_run(index: int, event: str, mode: str, request_timeout: int) -> dict:
    if index == 2:
        return {
            "run_index": index,
            "session_id": None,
            "started_at": "2026-08-06T00:00:00+00:00",
            "ended_at": "2026-08-06T00:00:01+00:00",
            "duration_ms": 500,
            "status": "failed",
            "all_agents_success": False,
            "evaluation_passed": False,
            "failed_agents": ["runtime"],
            "error": "RuntimeError: local failure",
        }
    return _success_run(index, event, mode, request_timeout)


class FakeQueue:
    def __init__(self, value=None):
        self.value = value

    def get_nowait(self):
        if self.value is None:
            raise runner.Empty()
        return self.value


class TimeoutProcess:
    terminated = False
    killed = False

    def __init__(self, target, args):
        self.exitcode = None
        self._alive = True

    def start(self):
        self._alive = True

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return self._alive

    def terminate(self):
        TimeoutProcess.terminated = True
        self._alive = False

    def kill(self):
        TimeoutProcess.killed = True
        self._alive = False


class SuccessProcess:
    def __init__(self, target, args):
        self.exitcode = 0
        self._alive = False

    def start(self):
        self._alive = False

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return self._alive


def test_parse_args_defaults():
    args = runner.parse_args([])

    assert args.runs == 5
    assert args.mode == "mock"
    assert args.request_timeout == 120
    assert args.output == runner.DEFAULT_OUTPUT_PATH


def test_parse_args_accepts_runs_mode_output_and_timeout(tmp_path):
    output = tmp_path / "report.json"

    args = runner.parse_args(
        [
            "--runs",
            "1",
            "--mode",
            "mock",
            "--request-timeout",
            "30",
            "--output",
            str(output),
        ]
    )

    assert args.runs == 1
    assert args.mode == "mock"
    assert args.request_timeout == 30
    assert args.output == output


@pytest.mark.parametrize("argv", [["--runs", "0"], ["--request-timeout", "0"]])
def test_parse_args_rejects_non_positive_values(argv):
    with pytest.raises(SystemExit):
        runner.parse_args(argv)


def test_run_reliability_writes_successful_run_and_summary(tmp_path):
    output = tmp_path / "nested" / "report.json"
    args = argparse.Namespace(runs=1, mode="mock", request_timeout=30, output=output)

    report = runner.run_reliability(args, run_once=_success_run)
    saved = json.loads(output.read_text(encoding="utf-8"))

    assert len(report["runs"]) == 1
    assert saved["runs"][0]["status"] == "success"
    assert saved["runs"][0]["session_id"] == "session-1"
    assert saved["summary"]["requested_runs"] == 1
    assert saved["summary"]["successful_runs"] == 1


def test_run_reliability_saves_incrementally_and_keeps_previous_results(tmp_path):
    output = tmp_path / "report.json"
    args = argparse.Namespace(runs=3, mode="mock", request_timeout=30, output=output)
    snapshots = []

    def capture_write(path, report):
        snapshots.append(json.loads(json.dumps(report)))
        runner.write_report_atomic(path, report)

    runner.run_reliability(args, run_once=_mixed_run, write_report=capture_write)

    assert [len(snapshot["runs"]) for snapshot in snapshots] == [0, 1, 2, 3]
    assert snapshots[2]["runs"][0]["status"] == "success"
    assert snapshots[2]["runs"][1]["status"] == "failed"
    assert snapshots[-1]["summary"]["successful_runs"] == 2
    assert snapshots[-1]["summary"]["failed_runs"] == 1


def test_run_once_with_process_timeout_terminates_child_process():
    TimeoutProcess.terminated = False
    TimeoutProcess.killed = False

    result = runner.run_once_with_process(
        index=1,
        event="event",
        mode="mock",
        request_timeout=1,
        process_factory=TimeoutProcess,
        queue_factory=lambda: FakeQueue(),
    )

    assert result["status"] == "timeout"
    assert result["all_agents_success"] is False
    assert result["evaluation_passed"] is False
    assert result["failed_agents"] == ["timeout"]
    assert "timed out" in result["error"]
    assert TimeoutProcess.terminated is True


def test_run_once_with_process_success_from_child():
    result = runner.run_once_with_process(
        index=1,
        event="event",
        mode="mock",
        request_timeout=10,
        process_factory=SuccessProcess,
        queue_factory=lambda: FakeQueue(
            {
                "run_index": 1,
                "session_id": "child-1",
                "status": "success",
                "all_agents_success": True,
                "evaluation_passed": True,
                "failed_agents": [],
                "error": None,
            }
        ),
    )

    assert result["status"] == "success"
    assert result["session_id"] == "child-1"
    assert result["duration_ms"] >= 0
    assert result["started_at"]
    assert result["ended_at"]


def test_build_summary_counts_statuses_and_average_duration():
    runs = [
        {"status": "success", "duration_ms": 100, "evaluation_passed": True},
        {"status": "failed", "duration_ms": 200, "evaluation_passed": False},
        {"status": "timeout", "duration_ms": 300, "evaluation_passed": False},
    ]

    summary = runner.build_summary(runs, requested_runs=3)

    assert summary["requested_runs"] == 3
    assert summary["completed_runs"] == 2
    assert summary["successful_runs"] == 1
    assert summary["failed_runs"] == 1
    assert summary["timeout_runs"] == 1
    assert summary["evaluation_passed_runs"] == 1
    assert summary["average_duration_ms"] == 200
    assert summary["successful_runs"] + summary["failed_runs"] + summary["timeout_runs"] == len(runs)


def test_output_is_safe_and_json_can_be_reloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    output = tmp_path / "missing" / "report.json"
    args = argparse.Namespace(runs=1, mode="mock", request_timeout=30, output=output)

    runner.run_reliability(args, run_once=_success_run)

    raw_text = output.read_text(encoding="utf-8")
    saved = json.loads(raw_text)
    assert saved["config"]["mode"] == "mock"
    assert "secret-test-key" not in raw_text
    assert "Authorization" not in raw_text
    assert "Prompt" not in raw_text


def test_configure_runtime_mock_mode_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    runner.configure_runtime("mock", 30)

    assert runner.os.environ["AGENT_MODE"] == "mock"
    assert runner.os.environ["LLM_TIMEOUT_SECONDS"] == "30"
