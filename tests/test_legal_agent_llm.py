from backend.agents import legal_agent


TEST_PAYLOAD = {
    "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。",
    "draft": "我们已关注到相关情况，并已启动核查，将持续同步进展。",
    "redteam_review": {
        "issues": ["声明较模板化", "缺少具体整改动作"],
        "attack_summary": "公众可能质疑企业只是程序化回应。",
        "suggestions": ["补充核查范围", "说明后续整改和更新时间"],
    },
}
EXPECTED_FIELDS = {
    "legal_risks",
    "safe_points",
    "revision_advice",
    "public_opinion_suggestions",
    "integrated_revision_tasks",
}


def test_legal_agent_llm_without_api_key_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {"context": "", "sources": [], "chunks": []},
    )

    result = legal_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) >= EXPECTED_FIELDS
    assert all(isinstance(result[field], list) for field in EXPECTED_FIELDS)


def test_legal_agent_llm_invalid_json_fallbacks_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {"context": "法律风险规范", "sources": [], "chunks": []},
    )
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: "not json")

    result = legal_agent.run(TEST_PAYLOAD)

    assert set(result.keys()) >= EXPECTED_FIELDS
    assert all(isinstance(result[field], list) for field in EXPECTED_FIELDS)


def test_legal_agent_llm_with_retrieval_context_parses_json(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[legal_risk_rules.md]\n避免提前定责，使用条件式责任表达。",
            "sources": [{"source": "legal_risk_rules.md", "score": 1.0}],
            "chunks": [
                {
                    "chunk_id": "legal_risk_rules.md#0",
                    "source": "legal_risk_rules.md",
                    "title": "法律风险表达规则",
                    "score": 1.0,
                    "rerank_score": 1.0,
                    "text": "避免提前定责，使用条件式责任表达。",
                }
            ],
        },
    )

    def fake_call_llm(prompt):
        assert "合规审查 Agent B" in prompt
        assert "retrieved_context" in prompt
        assert "避免提前定责" in prompt
        assert TEST_PAYLOAD["redteam_review"]["attack_summary"] in prompt
        return """
        {
          "legal_risks": ["避免在核查完成前确认事实"],
          "safe_points": ["已使用启动核查的审慎表达"],
          "revision_advice": ["责任表述应加入核查结果前提"],
          "public_opinion_suggestions": ["补充核查范围", "说明后续整改和更新时间"],
          "integrated_revision_tasks": ["补充核查范围并避免绝对化表达"],
          "legal_safety_score_hint": 8,
          "review_summary": "已结合 RAG 合规知识和红队反馈完成审查。"
        }
        """

    monkeypatch.setattr(legal_agent, "call_llm", fake_call_llm)

    result = legal_agent.run(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert result["legal_risks"] == ["避免在核查完成前确认事实"]
    assert result["public_opinion_suggestions"] == ["补充核查范围", "说明后续整改和更新时间"]
    assert result["integrated_revision_tasks"] == ["补充核查范围并避免绝对化表达"]
    assert result["legal_safety_score_hint"] == 8
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is True
    assert rag_info["sources"] == ["legal_risk_rules.md"]
