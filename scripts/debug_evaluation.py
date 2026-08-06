import json
import os
import sys
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
from backend.evaluation.metrics import score_empathy, score_legal_safety, score_robustness


DEMO_EVENT = (
    "\u67d0\u98df\u54c1\u54c1\u724c\u88ab\u66dd\u5149\u4f7f\u7528"
    "\u8fc7\u671f\u539f\u6599\uff0c\u76f8\u5173\u89c6\u9891\u5728"
    "\u7f51\u7edc\u4f20\u64ad\uff0c\u6d88\u8d39\u8005\u8981\u6c42"
    "\u76d1\u7ba1\u4ecb\u5165"
)
OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "outputs" / "real_llm_demo_debug.json"


def main() -> int:
    os.environ["AGENT_MODE"] = "llm"
    get_config.cache_clear()

    runtime_result = run_dynamic_agent(DEMO_EVENT)
    results = runtime_result.get("results", {})
    decision_result = results.get("decision", {})
    final_statement = decision_result.get("final_statement", "")
    agent_trace = runtime_result.get("execution_trace", [])

    legal_metric = score_legal_safety(final_statement)
    empathy_metric = score_empathy(final_statement)
    robustness_metric = score_robustness(results, final_statement, agent_trace)
    evaluation_result = evaluate_agent_run(
        event=runtime_result.get("event", DEMO_EVENT),
        results=results,
        final_statement=final_statement,
        agent_trace=agent_trace,
    )

    debug_result = {
        "event": runtime_result.get("event", DEMO_EVENT),
        "session_id": runtime_result.get("session_id"),
        "executed_agents": runtime_result.get("executed_agents", []),
        "failed_agents": runtime_result.get("failed_agents", []),
        "final_statement": final_statement,
        "decision_scores": decision_result.get("scores", {}),
        "decision_result": decision_result,
        "evaluation_result": evaluation_result,
        "metric_breakdown": {
            "legal_safety": legal_metric,
            "empathy": empathy_metric,
            "robustness": robustness_metric,
        },
        "thresholds": {
            "legal_safety": 7,
            "empathy": 6,
            "robustness": 6,
        },
        "agent_trace": agent_trace,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(debug_result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(debug_result, ensure_ascii=False, indent=2))
    print(f"\nSaved debug output to: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
