import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["AGENT_MODE"] = "llm"
os.environ["LLM_API_KEY"] = ""


from backend.agents.sentiment_agent import run


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def main() -> None:
    result = run(TEST_EVENT)
    print(
        json.dumps(
            {
                "mode": "llm_with_mock_fallback",
                "event": TEST_EVENT,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
