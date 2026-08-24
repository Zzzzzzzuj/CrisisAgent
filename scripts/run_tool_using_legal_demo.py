import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.tool_using_legal_agent import run
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    registry = _demo_registry()
    cases = [
        {
            "name": "high_risk_food_safety",
            "payload": {
                "event": "某食品品牌被曝光使用过期原料，相关视频传播，消费者要求监管介入。",
                "sentiment_result": {"risk_level": "high", "public_emotion": "angry"},
                "redteam_result": {"issues": ["可能被质疑逃避责任"], "suggestions": ["补充核查和召回安排"]},
                "draft": "我们正在了解情况。",
            },
        },
        {
            "name": "low_risk_customer_service",
            "payload": {
                "event": "用户反馈商品包装轻微破损，希望客服协助补发。",
                "sentiment_result": {"risk_level": "low", "public_emotion": "calm"},
                "redteam_result": {"issues": [], "suggestions": []},
                "draft": "客服会尽快处理。",
            },
        },
    ]
    results = []
    for case in cases:
        result = run(case["payload"], registry=registry)
        summary = {
            "case": case["name"],
            "plan": result["tool_plan"],
            "tool_calls": [
                {
                    "name": item.get("name"),
                    "success": item.get("success"),
                    "policy": item.get("policy"),
                }
                for item in result["tool_call_trace"]
            ],
            "observations": [
                {
                    "tool": item.get("tool"),
                    "success": item.get("success"),
                    "output_keys": sorted((item.get("output") or {}).keys()),
                }
                for item in result["tool_observations"]
            ],
            "final_legal_review": {
                "legal_risks": result["legal_risks"],
                "safe_points": result["safe_points"],
                "revision_advice": result["revision_advice"],
                "human_review_required": result["human_review_required"],
            },
        }
        results.append(summary)
        print(f"\n## {case['name']}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("\nDemo summary:")
    print(
        json.dumps(
            {
                "cases": len(results),
                "high_risk_tools": results[0]["plan"]["required_tools"],
                "low_risk_skipped_tools": results[1]["plan"]["skipped_tools"],
                "all_cases_completed": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _demo_registry() -> SkillRegistry:
    return SkillRegistry(
        [
            AgentSkill(
                name="legal_rag_search",
                description="Demo Legal RAG search.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                category="rag",
                owner_agent="legal_agent",
                safety_level="medium",
                enabled=True,
                version="demo",
                handler=lambda payload: {
                    "context": "食品安全事件需先核查批次、保存证据并配合监管。",
                    "sources": [{"source": "food_safety.md", "source_category": "food_safety"}],
                    "chunks": [
                        {
                            "chunk_id": "food_safety:v1:chunk-0",
                            "text_preview": "核查批次、监管沟通、必要时召回。",
                            "score": 0.82,
                            "rerank_score": 0.76,
                        }
                    ],
                    "fallback_used": False,
                },
            ),
            AgentSkill(
                name="guardrail_check",
                description="Demo guardrail check.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "event": {"type": "string"},
                        "statement": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                category="safety",
                owner_agent="guardrails",
                safety_level="high",
                enabled=True,
                version="demo",
                handler=lambda payload: {"input": {"hit": False}, "output": {"hit": False}, "hit": False},
            ),
            AgentSkill(
                name="knowledge_document_search",
                description="Demo knowledge document search.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "source_category": {"type": "string"},
                        "published_only": {"type": "boolean"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                category="knowledge",
                owner_agent="legal_agent",
                safety_level="low",
                enabled=True,
                version="demo",
                handler=lambda payload: {"documents": [{"source_name": "food_safety.md"}], "count": 1},
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
