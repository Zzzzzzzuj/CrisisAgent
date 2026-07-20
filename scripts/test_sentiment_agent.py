import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.agents.sentiment_agent import run


TEST_EVENT = "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"


def main() -> None:
    result = run(TEST_EVENT)

    print("Agent A result:")
    print(f"risk_level: {result['risk_level']}")
    print(f"public_emotion: {result['public_emotion']}")
    print(f"keywords: {result['keywords']}")
    print(f"recommended_tone: {result['recommended_tone']}")
    print(f"analysis_summary: {result['analysis_summary']}")


if __name__ == "__main__":
    main()
