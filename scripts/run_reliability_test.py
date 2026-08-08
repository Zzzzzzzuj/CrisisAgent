import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)

from backend.config import get_config
from backend.core.dynamic_runtime import run_dynamic_agent
from backend.evaluation import evaluate_agent_run
from backend.llm.config import get_llm_config


DEFAULT_RUNS = 5
DEFAULT_MODE = "mock"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "outputs" / "reliability_report.json"
DEMO_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。"
EXPECTED_AGENTS = ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
DECISION_SCORE_FIELDS = ("legal_safety", "empathy", "robustness")
EVALUATION_SCORE_FIELDS = ("legal_safety_score", "empathy_score", "robustness_score")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_runtime(args.mode, args.request_timeout)
    run_reliability(args)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CrisisAgent reliability checks.")
    parser.add_argument("--runs", type=_positive_int, default=DEFAULT_RUNS)
    parser.add_argument("--mode", choices=("mock", "llm"), default=DEFAULT_MODE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--request-timeout", type=_positive_int, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def configure_runtime(mode: str, request_timeout: int) -> None:
    os.environ["AGENT_MODE"] = mode
    os.environ["LLM_TIMEOUT_SECONDS"] = str(request_timeout)
    get_config.cache_clear()
    get_llm_config.cache_clear()


def run_reliability(args: argparse.Namespace, run_once=None, write_report=None) -> dict:
    run_once = run_once or run_once_with_process
    write_report = write_report or write_report_atomic
    output_path = _resolve_output_path(args.output)
    report = _initial_report(args)

    write_report(output_path, report)
    for index in range(1, args.runs + 1):
        print(f"Running reliability test {index}/{args.runs} mode={args.mode}...")
        run_result = run_once(
            index=index,
            event=DEMO_EVENT,
            mode=args.mode,
            request_timeout=args.request_timeout,
        )
        report["runs"].append(run_result)
        report["summary"] = build_summary(report["runs"], requested_runs=args.runs)
        write_report(output_path, report)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved reliability report to: {output_path}")
    return report


def run_once_with_process(
    index: int,
    event: str,
    mode: str,
    request_timeout: int,
    worker=None,
    process_factory=None,
    queue_factory=None,
) -> dict:
    worker = worker or workflow_worker
    process_factory = process_factory or Process
    queue_factory = queue_factory or Queue
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    result_queue = queue_factory()
    process = process_factory(target=worker, args=(index, event, mode, result_queue))
    process.start()
    process.join(request_timeout)

    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(5)
        return _timeout_result(index, started_at, started_monotonic, request_timeout)

    try:
        child_result = result_queue.get_nowait()
    except Empty:
        error = f"Child process exited without result. exitcode={process.exitcode}"
        child_result = _failed_result(index=index, session_id=None, failed_agents=["runtime"], error=error)

    return _with_timing(child_result, started_at, started_monotonic)


def workflow_worker(index: int, event: str, mode: str, result_queue: Queue) -> None:
    try:
        configure_runtime(mode, int(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))))
        result_queue.put(execute_workflow_run(index, event))
    except Exception as exc:
        result_queue.put(
            _failed_result(
                index=index,
                session_id=None,
                failed_agents=["runtime"],
                error=_safe_error(exc),
            )
        )


def execute_workflow_run(index: int, event: str) -> dict:
    runtime_result = run_dynamic_agent(event)
    results = runtime_result.get("results", {})
    decision_result = results.get("decision", {})
    final_statement = decision_result.get("final_statement", "")
    evaluation_result = evaluate_agent_run(
        event=runtime_result.get("event", event),
        results=results,
        final_statement=final_statement,
        agent_trace=runtime_result.get("execution_trace", []),
    )
    executed_agents = runtime_result.get("executed_agents", [])
    failed_agents = runtime_result.get("failed_agents", [])
    all_agents_success = _is_agent_success(executed_agents, failed_agents)

    return {
        "run_index": index,
        "session_id": runtime_result.get("session_id"),
        "status": "success" if all_agents_success else "failed",
        "all_agents_success": all_agents_success,
        "evaluation_passed": bool(evaluation_result.get("passed")),
        "failed_agents": failed_agents,
        "error": None if all_agents_success else "One or more agents failed.",
        "executed_agents": executed_agents,
        "human_gate_status": _extract_human_gate_status(runtime_result),
        "final_statement": final_statement,
        "decision_scores": _normalize_scores(decision_result.get("scores", {}), DECISION_SCORE_FIELDS),
        "evaluation_scores": _normalize_scores(evaluation_result, EVALUATION_SCORE_FIELDS),
        "recommendation": decision_result.get("recommendation", ""),
        "evaluation_result": evaluation_result,
    }


def build_summary(runs: list[dict], requested_runs: int) -> dict:
    successful_runs = sum(1 for item in runs if item.get("status") == "success")
    failed_runs = sum(1 for item in runs if item.get("status") == "failed")
    timeout_runs = sum(1 for item in runs if item.get("status") == "timeout")
    completed_runs = successful_runs + failed_runs
    evaluation_passed_runs = sum(1 for item in runs if item.get("evaluation_passed") is True)
    recommendation_counts = Counter(
        item.get("recommendation", "") for item in runs if item.get("status") == "success" and item.get("recommendation")
    )
    average_duration_ms = _average_duration_ms(runs)

    return {
        "requested_runs": requested_runs,
        "completed_runs": completed_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "timeout_runs": timeout_runs,
        "evaluation_passed_runs": evaluation_passed_runs,
        "average_duration_ms": average_duration_ms,
        "agent_success_rate": _ratio(successful_runs, len(runs)),
        "evaluation_pass_rate": _ratio(evaluation_passed_runs, len(runs)),
        "recommendation_counts": dict(recommendation_counts),
        "recommendation_consistency": _recommendation_consistency(recommendation_counts, successful_runs),
        "average_decision_scores": _average_score(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "average_evaluation_scores": _average_score(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
        "decision_score_ranges": _score_ranges(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "evaluation_score_ranges": _score_ranges(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
        "max_decision_score_variation": _max_score_variation(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "max_evaluation_score_variation": _max_score_variation(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
    }


def write_report_atomic(output_path: Path, report: dict) -> None:
    output_path = _resolve_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    temp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, output_path)


def _initial_report(args: argparse.Namespace) -> dict:
    return {
        "case": {
            "event": DEMO_EVENT,
            "risk_level": "high",
        },
        "config": {
            "requested_runs": args.runs,
            "mode": args.mode,
            "request_timeout_seconds": args.request_timeout,
        },
        "summary": build_summary([], requested_runs=args.runs),
        "runs": [],
    }


def _timeout_result(index: int, started_at: str, started_monotonic: float, request_timeout: int) -> dict:
    return {
        "run_index": index,
        "session_id": None,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": _duration_ms(started_monotonic),
        "status": "timeout",
        "all_agents_success": False,
        "evaluation_passed": False,
        "failed_agents": ["timeout"],
        "error": f"Run timed out after {request_timeout} seconds.",
    }


def _failed_result(index: int, session_id, failed_agents: list, error: str) -> dict:
    return {
        "run_index": index,
        "session_id": session_id,
        "status": "failed",
        "all_agents_success": False,
        "evaluation_passed": False,
        "failed_agents": failed_agents,
        "error": error,
        "executed_agents": [],
        "human_gate_status": "unknown",
        "final_statement": "",
        "decision_scores": _zero_scores(DECISION_SCORE_FIELDS),
        "evaluation_scores": _zero_scores(EVALUATION_SCORE_FIELDS),
        "recommendation": "",
        "evaluation_result": {},
    }


def _with_timing(result: dict, started_at: str, started_monotonic: float) -> dict:
    timed_result = dict(result)
    timed_result["started_at"] = started_at
    timed_result["ended_at"] = _now_iso()
    timed_result["duration_ms"] = _duration_ms(started_monotonic)
    timed_result.setdefault("session_id", None)
    timed_result.setdefault("status", "failed")
    timed_result.setdefault("all_agents_success", False)
    timed_result.setdefault("evaluation_passed", False)
    timed_result.setdefault("failed_agents", [])
    timed_result.setdefault("error", None)
    return timed_result


def _safe_error(exc: Exception, limit: int = 500) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:limit]}"


def _is_agent_success(executed_agents: list[str], failed_agents: list) -> bool:
    return executed_agents == EXPECTED_AGENTS and not failed_agents


def _extract_human_gate_status(runtime_result: dict) -> str:
    return (
        runtime_result.get("state_status")
        or runtime_result.get("status")
        or runtime_result.get("approval", {}).get("decision")
        or "not_applicable"
    )


def _normalize_scores(data: dict, fields: tuple[str, ...]) -> dict:
    scores = {}
    for field in fields:
        try:
            scores[field] = int(data.get(field, 0))
        except (TypeError, ValueError):
            scores[field] = 0
    return scores


def _zero_scores(fields: tuple[str, ...]) -> dict:
    return {field: 0 for field in fields}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _recommendation_consistency(counts: Counter, total: int) -> float:
    if total == 0 or not counts:
        return 0.0
    return round(max(counts.values()) / total, 4)


def _average_duration_ms(runs: list[dict]) -> float:
    durations = [item.get("duration_ms", 0) for item in runs]
    return round(sum(durations) / len(durations), 2) if durations else 0.0


def _average_score(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> dict:
    averages = {}
    successful_runs = [item for item in runs if item.get("status") == "success"]
    for field in fields:
        values = [item.get(score_key, {}).get(field, 0) for item in successful_runs]
        averages[field] = round(sum(values) / len(values), 2) if values else 0.0
    return averages


def _score_ranges(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> dict:
    ranges = {}
    successful_runs = [item for item in runs if item.get("status") == "success"]
    for field in fields:
        values = [item.get(score_key, {}).get(field, 0) for item in successful_runs]
        ranges[field] = {
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "variation": (max(values) - min(values)) if values else 0,
        }
    return ranges


def _max_score_variation(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> int:
    ranges = _score_ranges(runs, score_key, fields)
    return max(item["variation"] for item in ranges.values()) if ranges else 0


def _duration_ms(started_monotonic: float) -> int:
    return max(0, int((time.monotonic() - started_monotonic) * 1000))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def _resolve_output_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
