import pytest

from backend.agents import writer_agent
from backend.config import get_config


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "first_draft": {
        "statement": "我们已关注到相关情况，并已启动核查。",
        "strategy": "快速回应。",
        "tone": "先共情、再回应行动、避免抢先定性",
        "notes": "第一版。",
    },
    "redteam_review": {
        "issues": ["声明较模板化", "缺少具体整改动作"],
        "attack_summary": "公众可能质疑企业只是程序化回应。",
        "suggestions": ["补充核查范围", "说明后续整改和更新时间"],
    },
    "legal_review": {
        "revision_advice": ["责任表述应加入核查结果前提"],
        "integrated_revision_tasks": ["补充核查范围并避免绝对化表达"],
        "public_opinion_suggestions": ["说明后续整改和更新时间"],
        "review_summary": "整体稳妥，但需增强行动说明。",
    },
}
EXPECTED_FIELDS = {
    "statement",
    "strategy",
    "tone",
    "revisions",
    "revisions_from_v1",
    "review_summary",
}


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_writer_v2_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    result = writer_agent.generate_second_draft(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert result["statement"]
    assert isinstance(result["revisions"], list)
    assert result["revisions_from_v1"] == result["revisions"]


def test_writer_v2_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr(writer_agent, "call_llm", lambda prompt: "not json")

    result = writer_agent.generate_second_draft(TEST_PAYLOAD)

    assert set(result.keys()) == EXPECTED_FIELDS
    assert result["statement"]
    assert isinstance(result["revisions"], list)


def test_writer_v2_llm_valid_json_is_parsed(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def fake_call_llm(prompt):
        assert "Writer_v2 Revision Agent" in prompt
        assert "危机公关高级文案专家" in prompt
        assert TEST_PAYLOAD["first_draft"]["statement"] in prompt
        assert "integrated_revision_tasks" in prompt
        return """
        {
          "statement": "我们已关注到相关情况，并充分理解公众担忧。公司已启动专项核查，并将配合监管、持续同步进展。",
          "strategy": "吸收红队和合规建议，强化行动和公众沟通。",
          "tone": "先共情、再回应行动、避免抢先定性",
          "revisions": ["补充专项核查", "增加监管配合", "强化公众沟通"]
        }
        """

    monkeypatch.setattr(writer_agent, "call_llm", fake_call_llm)

    result = writer_agent.generate_second_draft(TEST_PAYLOAD)

    assert result["statement"] == "我们已关注到相关情况，并充分理解公众担忧。公司已启动专项核查，并将配合监管、持续同步进展。"
    assert result["strategy"] == "吸收红队和合规建议，强化行动和公众沟通。"
    assert result["tone"] == "先共情、再回应行动、避免抢先定性"
    assert result["revisions"] == ["补充专项核查", "增加监管配合", "强化公众沟通"]
    assert result["revisions_from_v1"] == result["revisions"]
    assert result["review_summary"]["integrated_revision_tasks"] == ["补充核查范围并避免绝对化表达"]
