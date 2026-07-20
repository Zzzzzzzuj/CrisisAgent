from backend.agents import decision_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "second_draft": (
        "我们已注意到关于此事的相关传播内容，并充分理解公众对此产生的担忧与关切。"
        "公司已立即启动专项核查，对相关原料、生产流程、仓储管理及涉事批次进行全面排查。"
        "如核查发现任何违反食品安全要求的情形，我们将严肃处理并依法依规承担相应责任。"
        "目前，我们正同步配合监管部门开展调查，并将根据核查进展持续对外说明。"
        "对于给消费者和合作伙伴带来的不安，我们再次表示歉意。"
    ),
    "sentiment_analysis": {
        "risk_level": "high",
        "public_emotion": "angry",
        "keywords": ["过期原料", "传播视频", "监管介入"],
        "recommended_tone": "先共情、再回应行动、避免抢先定性",
        "analysis_summary": "当前事件具有较强传播性和监管敏感性。",
    },
    "redteam_review": {
        "issues": ["可能被解读为企业在拖延表态。", "只提排查，未说明后续整改与问责动作。"],
        "attack_summary": "公众和媒体可能质疑回应过于模板化。",
        "suggestions": ["补充核查范围和后续处理承诺。"],
    },
    "legal_review": {
        "legal_risks": ["未发现明显高风险承认性表述。"],
        "safe_points": ["使用了配合监管等稳妥表达。"],
        "revision_advice": ["避免提前定责。"],
        "public_opinion_suggestions": ["更明确回应消费者担忧。"],
        "integrated_revision_tasks": ["补充整改动作。"],
        "legal_safety_score_hint": 8,
        "review_summary": "当前草稿整体偏稳妥。",
    },
}


def test_decision_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == {"final_statement", "scores", "decision_summary"}
    assert isinstance(result["final_statement"], str)
    assert isinstance(result["scores"], dict)
    assert isinstance(result["decision_summary"], str)
    assert set(result["scores"].keys()) == {"legal_safety", "empathy", "robustness"}
    assert all(isinstance(result["scores"][field], int) for field in result["scores"])


def test_decision_agent_llm_mode_success(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        decision_agent,
        "call_llm",
        lambda prompt: """
        ```json
        {
          "final_statement": "我们已启动核查，并将持续说明进展。",
          "scores": {
            "legal_safety": 8,
            "empathy": 8,
            "robustness": 7
          },
          "decision_summary": "当前版本适合作为对外回应底稿。"
        }
        ```
        """,
    )

    result = decision_agent.run(TEST_PAYLOAD)

    assert result == {
        "final_statement": "我们已启动核查，并将持续说明进展。",
        "scores": {
            "legal_safety": 8,
            "empathy": 8,
            "robustness": 7,
        },
        "decision_summary": "当前版本适合作为对外回应底稿。",
    }


def test_decision_agent_llm_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        decision_agent,
        "call_llm",
        lambda prompt: '{"final_statement": "missing scores and summary"}',
    )

    result = decision_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) == {"final_statement", "scores", "decision_summary"}
    assert set(result["scores"].keys()) == {"legal_safety", "empathy", "robustness"}
