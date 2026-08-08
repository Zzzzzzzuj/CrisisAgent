from backend.agents import decision_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被曝光使用过期原料，消费者要求监管介入。",
    "writer_v2": {
        "statement": (
            "我们对受到影响的消费者表示歉意，并已启动专项核查。"
            "公司将配合监管部门调查，启动召回和整改，并持续更新进展。"
        )
    },
    "legal_review": {
        "legal_risks": [],
        "revision_advice": ["避免提前定责"],
        "integrated_revision_tasks": ["补充监管沟通和后续措施"],
    },
    "redteam_review": {
        "issues": ["需要更具体的行动计划"],
        "suggestions": ["补充召回、整改和信息公开安排"],
    },
    "evaluation": {
        "legal_safety_score": 10,
        "empathy_score": 10,
        "robustness_score": 10,
        "passed": True,
    },
}


def test_decision_prompt_contains_stability_rubric():
    prompt = decision_agent._build_decision_prompt(TEST_PAYLOAD)

    assert "企业危机响应首席决策官" in prompt
    assert "不是重新生成声明" in prompt
    assert "必须直接使用 Writer_v2 statement" in prompt
    assert "legal_safety 评分规则" in prompt
    assert "empathy 评分规则" in prompt
    assert "robustness 评分规则" in prompt
    assert "不要过度降低评分" in prompt


def test_decision_prompt_stability_valid_json_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    def fake_call_llm(prompt):
        assert "recommendation 必须是 publish / revise / hold 之一" in prompt
        return """
        {
          "final_statement": "我们对受到影响的消费者表示歉意，并已启动专项核查。公司将配合监管部门调查，启动召回和整改，并持续更新进展。",
          "scores": {
            "legal_safety": 9,
            "empathy": 9,
            "robustness": 9
          },
          "recommendation": "publish",
          "reason": "声明包含共情、核查、监管沟通和后续整改安排，适合公开发布。"
        }
        """

    monkeypatch.setattr(decision_agent, "call_llm", fake_call_llm)

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == {
        "final_statement",
        "scores",
        "recommendation",
        "reason",
        "decision_summary",
    }
    assert result["recommendation"] in {"publish", "revise", "hold"}
    assert all(0 <= score <= 10 for score in result["scores"].values())
    assert set(result["scores"].keys()) == {"legal_safety", "empathy", "robustness"}
