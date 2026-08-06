import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["AGENT_MODE"] = "llm"
os.environ["LLM_API_KEY"] = "demo-key"
os.environ["LLM_BASE_URL"] = "https://example.com/v1"
os.environ["LLM_MODEL"] = "demo-model"


from backend.agents import redteam_agent, sentiment_agent, writer_agent


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def main() -> None:
    sentiment_agent.call_llm = lambda prompt: (_ for _ in ()).throw(
        RuntimeError("demo fallback: sentiment llm unavailable")
    )
    writer_agent.call_llm = lambda prompt: (_ for _ in ()).throw(
        RuntimeError("demo fallback: writer llm unavailable")
    )
    redteam_agent.call_llm = lambda prompt: (_ for _ in ()).throw(
        RuntimeError("demo fallback: redteam llm unavailable")
    )

    sentiment = sentiment_agent.run(TEST_EVENT)
    writer_result = writer_agent.run(
        {
            "event": TEST_EVENT,
            "sentiment_analysis": sentiment,
        }
    )
    redteam_result = redteam_agent.run(
        {
            "event": TEST_EVENT,
            "draft": writer_result["statement"],
        }
    )

    print(
        json.dumps(
            {
                "mode": "llm_with_mock_fallback",
                "event": TEST_EVENT,
                "sentiment_analysis": sentiment,
                "writer_result": writer_result,
                "redteam_result": redteam_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
