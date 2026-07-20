from backend.agents import legal_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "draft": (
        "我们已关注到关于本次事件的网络反馈，对由此引发的公众担忧深表重视。"
        "公司已第一时间启动内部核查程序，对涉及批次、采购与生产环节展开全面排查。"
        "在事实进一步核实前，我们将及时同步调查进展，并积极配合相关监管要求。"
        "对于事件给消费者带来的不安，我们表示诚挚歉意。"
    ),
    "redteam_review": {
        "issues": ["可能被解读为企业在拖延表态。"],
        "attack_summary": "公众和媒体可能质疑回应过于模板化。",
        "suggestions": ["更明确表达对消费者担忧的理解。", "补充核查范围和后续处理承诺。"],
    },
}


def test_legal_agent_mock_mode_returns_expected_schema(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    get_config.cache_clear()

    result = legal_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) >= {
        "legal_risks",
        "safe_points",
        "revision_advice",
        "public_opinion_suggestions",
        "integrated_revision_tasks",
    }
    assert isinstance(result["legal_risks"], list)
    assert isinstance(result["safe_points"], list)
    assert isinstance(result["revision_advice"], list)
    assert isinstance(result["public_opinion_suggestions"], list)
    assert isinstance(result["integrated_revision_tasks"], list)
    assert all(isinstance(item, str) for item in result["legal_risks"])
    assert all(isinstance(item, str) for item in result["safe_points"])
    assert all(isinstance(item, str) for item in result["revision_advice"])
    assert all(isinstance(item, str) for item in result["public_opinion_suggestions"])
    assert all(isinstance(item, str) for item in result["integrated_revision_tasks"])


def test_legal_agent_llm_mode_success(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(
        legal_agent,
        "call_llm",
        lambda prompt: """
        ```json
        {
          "legal_risks": ["避免提前认定全部事实。"],
          "safe_points": ["保留了配合监管的表述。"],
          "revision_advice": ["责任表述应加上调查结果前提。"],
          "public_opinion_suggestions": ["更明确回应消费者担忧。"],
          "integrated_revision_tasks": ["补充核查范围并避免绝对化表述。"],
          "legal_safety_score_hint": 8,
          "review_summary": "整体较稳妥，但仍需增强法律审慎性。"
        }
        ```
        """,
    )

    result = legal_agent.run(TEST_PAYLOAD)

    assert result["legal_risks"] == ["避免提前认定全部事实。"]
    assert result["safe_points"] == ["保留了配合监管的表述。"]
    assert result["revision_advice"] == ["责任表述应加上调查结果前提。"]
    assert result["public_opinion_suggestions"] == ["更明确回应消费者担忧。"]
    assert result["integrated_revision_tasks"] == ["补充核查范围并避免绝对化表述。"]


def test_legal_agent_llm_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: '{"legal_risks": ["only one field"]}')

    result = legal_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) >= {
        "legal_risks",
        "safe_points",
        "revision_advice",
        "public_opinion_suggestions",
        "integrated_revision_tasks",
    }
    assert isinstance(result["legal_risks"], list)
    assert isinstance(result["safe_points"], list)
