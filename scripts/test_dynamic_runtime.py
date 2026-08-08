import sys
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["AGENT_MODE"] = "mock"


from backend.core.agent_loop import run_agent_loop
from backend.core.dynamic_runtime import run_dynamic_agent


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
NO_HUMAN_POLICY = lambda state, evaluation: {"required": False, "reason": "", "triggers": []}


def main() -> None:
    runtime_result = run_dynamic_agent(TEST_EVENT)
    _print_runtime_result(runtime_result)
    _assert_dynamic_runtime(runtime_result)

    loop_result = run_agent_loop(TEST_EVENT, policy=NO_HUMAN_POLICY)
    _print_loop_result(loop_result)
    _assert_agent_loop(loop_result)

    print("dynamic runtime smoke test passed")


def _print_runtime_result(result: dict) -> None:
    print(f"session_id: {result['session_id']}")
    print(f"plan_id: {result['plan_id']}")
    print(f"event: {result['event']}")
    print("validated_plan:")
    for item in result["validated_plan"]["plan"]:
        print(f"- {item['agent']}: {item.get('reason', '')}")

    print("executed_agents:")
    for agent in result["executed_agents"]:
        print(f"- {agent}")

    print("failed_agents:")
    for item in result["failed_agents"]:
        print(f"- {item['agent']}: {item['reason']}")

    decision = result["results"].get("decision", {})
    print(f"decision status: {'success' if decision else 'missing'}")
    print(f"final_statement: {decision.get('final_statement', '')}")

    print("execution_trace:")
    for item in result["execution_trace"]:
        print(f"- {item['agent']} | {item['status']} | error={item['error']}")


def _print_loop_result(result: dict) -> None:
    latest_evaluation = result["iterations"][-1]["evaluation"] if result["iterations"] else {}
    print("agent_loop:")
    print(f"- status: {result['status']}")
    print(f"- stopped_reason: {result['stopped_reason']}")
    print(f"- evaluation_passed: {latest_evaluation.get('passed')}")


def _assert_dynamic_runtime(result: dict) -> None:
    expected_agents = ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]
    actual_agents = [item["agent"] for item in result["validated_plan"]["plan"]]
    if actual_agents != expected_agents:
        raise AssertionError(f"unexpected validated plan: {actual_agents}")
    if result["failed_agents"]:
        raise AssertionError(f"dynamic runtime has failed agents: {result['failed_agents']}")
    if not result["results"].get("writer_v2", {}).get("statement"):
        raise AssertionError("writer_v2 second_draft is missing")
    if not result["results"].get("decision"):
        raise AssertionError("decision result is missing")
    if result["results"]["decision"]["final_statement"] != result["results"]["writer_v2"]["statement"]:
        raise AssertionError("decision did not use writer_v2 second_draft")


def _assert_agent_loop(result: dict) -> None:
    latest_evaluation = result["iterations"][-1]["evaluation"] if result["iterations"] else {}
    if result["status"] != "completed":
        raise AssertionError(f"agent_loop did not complete: {result['status']}")
    if latest_evaluation.get("passed") is not True:
        raise AssertionError(f"agent_loop evaluation did not pass: {latest_evaluation}")


if __name__ == "__main__":
    main()
