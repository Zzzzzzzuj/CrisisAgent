import sys
from pathlib import Path
from datetime import datetime


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
        start_time = datetime.fromisoformat(item.start_time)
        end_time = datetime.fromisoformat(item.end_time)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        print(item.agent)
        print("-" * 9)
        print(f"name: {item.name}")
        print(f"mode: {item.mode}")
        print(f"status: {item.status}")
        print(f"fallback: {str(item.fallback).lower()}")
        print(f"start_time: {item.start_time}")
        print(f"end_time: {item.end_time}")
        print(f"duration: {duration_ms} ms")
        print()


if __name__ == "__main__":
    main()
