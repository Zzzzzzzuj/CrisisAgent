import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.schemas import CrisisRunRequest
from backend.workflow import run_crisis_workflow


def main() -> None:
    request = CrisisRunRequest(
        event="某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
    )
    response = run_crisis_workflow(request)

    print(f"session_id: {response.session_id}")
    print(f"final_statement: {response.final_statement}")
    print(f"scores: {response.scores.model_dump()}")
    print("agent_trace:")
    for item in response.agent_trace:
        print(f"- {item.agent}: {item.name}")


if __name__ == "__main__":
    main()
