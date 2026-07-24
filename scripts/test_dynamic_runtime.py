import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.core.dynamic_runtime import run_dynamic_agent


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def main() -> None:
    result = run_dynamic_agent(TEST_EVENT)

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

    print("execution_trace:")
    for item in result["execution_trace"]:
        print(f"- {item['agent']} | {item['status']} | error={item['error']}")


if __name__ == "__main__":
    main()
