import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["AGENT_MODE"] = "mock"

from backend.core.dynamic_runtime import run_dynamic_agent
from backend.evaluation import evaluate_agent_run


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def main() -> None:
    run_result = run_dynamic_agent(TEST_EVENT)
    results = run_result.get("results", {})
    final_statement = results.get("decision", {}).get("final_statement", "")
    evaluation_result = evaluate_agent_run(
        event=run_result["event"],
        results=results,
        final_statement=final_statement,
        agent_trace=run_result.get("execution_trace", []),
    )

    print(
        json.dumps(
            {
                "session_id": run_result["session_id"],
                "final_statement": final_statement,
                "evaluation_result": evaluation_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
