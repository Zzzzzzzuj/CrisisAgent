import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)

from backend.config import get_config
from backend.core.dynamic_runtime import run_dynamic_agent
from backend.evaluation import evaluate_agent_run


RUN_COUNT = 5
DEMO_EVENT = (
    "某食品品牌被曝光使用过期原料，相关视频在网络传播，"
    "消费者要求监管介入。"
)
OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "outputs" / "reliability_report.json"
EXPECTED_AGENTS = ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
DECISION_SCORE_FIELDS = ("legal_safety", "empathy", "robustness")
EVALUATION_SCORE_FIELDS = ("legal_safety_score", "empathy_score", "robustness_score")


def main() -> int:
    _force_llm_mode()

    runs = []
    for index in range(1, RUN_COUNT + 1):
        print(f"Running reliability test {index}/{RUN_COUNT}...")
        runs.append(_run_once(index))

    report = {
        "case": {
            "event": DEMO_EVENT,
            "risk_level": "high",
        },
        "run_count": RUN_COUNT,
        "summary": _build_summary(runs),
        "runs": runs,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved reliability report to: {OUTPUT_PATH}")
    return 0


def _force_llm_mode() -> None:
    os.environ["AGENT_MODE"] = "llm"
    get_config.cache_clear()


def _run_once(index: int) -> dict:
    try:
        runtime_result = run_dynamic_agent(DEMO_EVENT)
        results = runtime_result.get("results", {})
        decision_result = results.get("decision", {})
        final_statement = decision_result.get("final_statement", "")
        evaluation_result = evaluate_agent_run(
            event=runtime_result.get("event", DEMO_EVENT),
            results=results,
            final_statement=final_statement,
            agent_trace=runtime_result.get("execution_trace", []),
        )
        executed_agents = runtime_result.get("executed_agents", [])
        failed_agents = runtime_result.get("failed_agents", [])

        return {
            "run_index": index,
            "status": "completed",
            "session_id": runtime_result.get("session_id"),
            "agent_success": _is_agent_success(executed_agents, failed_agents),
            "executed_agents": executed_agents,
            "failed_agents": failed_agents,
            "human_gate_status": _extract_human_gate_status(runtime_result),
            "final_statement": final_statement,
            "decision_scores": _normalize_scores(
                decision_result.get("scores", {}),
                DECISION_SCORE_FIELDS,
            ),
            "evaluation_scores": _normalize_scores(
                evaluation_result,
                EVALUATION_SCORE_FIELDS,
            ),
            "recommendation": decision_result.get("recommendation", ""),
            "evaluation_passed": bool(evaluation_result.get("passed")),
            "evaluation_result": evaluation_result,
        }
    except Exception as exc:
        return {
            "run_index": index,
            "status": "failed",
            "session_id": None,
            "agent_success": False,
            "executed_agents": [],
            "failed_agents": ["runtime"],
            "human_gate_status": "unknown",
            "final_statement": "",
            "decision_scores": _zero_scores(DECISION_SCORE_FIELDS),
            "evaluation_scores": _zero_scores(EVALUATION_SCORE_FIELDS),
            "recommendation": "",
            "evaluation_passed": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _is_agent_success(executed_agents: list[str], failed_agents: list[str]) -> bool:
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


def _build_summary(runs: list[dict]) -> dict:
    completed_runs = [item for item in runs if item.get("status") == "completed"]
    recommendation_counts = Counter(
        item.get("recommendation", "") for item in completed_runs if item.get("recommendation")
    )

    return {
        "total_runs": len(runs),
        "completed_runs": len(completed_runs),
        "agent_success_rate": _ratio(
            sum(1 for item in runs if item.get("agent_success")),
            len(runs),
        ),
        "evaluation_pass_rate": _ratio(
            sum(1 for item in runs if item.get("evaluation_passed")),
            len(runs),
        ),
        "recommendation_counts": dict(recommendation_counts),
        "recommendation_consistency": _recommendation_consistency(recommendation_counts, len(completed_runs)),
        "average_decision_scores": _average_score(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "average_evaluation_scores": _average_score(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
        "decision_score_ranges": _score_ranges(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "evaluation_score_ranges": _score_ranges(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
        "max_decision_score_variation": _max_score_variation(runs, "decision_scores", DECISION_SCORE_FIELDS),
        "max_evaluation_score_variation": _max_score_variation(runs, "evaluation_scores", EVALUATION_SCORE_FIELDS),
        "failed_run_count": sum(1 for item in runs if item.get("status") != "completed"),
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _recommendation_consistency(counts: Counter, total: int) -> float:
    if total == 0 or not counts:
        return 0.0
    return round(max(counts.values()) / total, 4)


def _average_score(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> dict:
    averages = {}
    for field in fields:
        values = [
            item.get(score_key, {}).get(field, 0)
            for item in runs
            if item.get("status") == "completed"
        ]
        averages[field] = round(sum(values) / len(values), 2) if values else 0.0
    return averages


def _score_ranges(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> dict:
    ranges = {}
    for field in fields:
        values = [
            item.get(score_key, {}).get(field, 0)
            for item in runs
            if item.get("status") == "completed"
        ]
        ranges[field] = {
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "variation": (max(values) - min(values)) if values else 0,
        }
    return ranges


def _max_score_variation(runs: list[dict], score_key: str, fields: tuple[str, ...]) -> int:
    ranges = _score_ranges(runs, score_key, fields)
    return max(item["variation"] for item in ranges.values()) if ranges else 0


if __name__ == "__main__":
    raise SystemExit(main())
