from backend.agents import legal_agent
from backend.config import get_config


def _gate_result(need_rag: bool) -> dict:
    return {
        "need_rag": need_rag,
        "intent": "crisis_response_needed" if need_rag else "information_lookup",
        "decision_score": 5 if need_rag else -3,
        "reason": "test gate result",
        "matched_signals": ["current_response_need"] if need_rag else [],
        "negative_signals": [] if need_rag else ["information_lookup"],
        "current_incident": need_rag,
        "current_incident_signals": ["current_response_need"] if need_rag else [],
        "task_intent": "ambiguous_enterprise_risk" if need_rag else "information_lookup",
        "decision_path": "current_incident_override" if need_rag else "non_current_task_reject",
    }


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

    def fail_gate_if_called(*args, **kwargs):
        raise AssertionError("gate should not be called in mock mode")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("retriever should not be called in mock mode")

    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", fail_gate_if_called)
    monkeypatch.setattr(legal_agent, "retrieve", fail_if_called)

    result = legal_agent.run(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert set(result.keys()) >= {
        "legal_risks",
        "safe_points",
        "revision_advice",
        "public_opinion_suggestions",
        "integrated_revision_tasks",
        "legal_safety_score_hint",
        "review_summary",
    }
    assert isinstance(result["legal_risks"], list)
    assert isinstance(result["safe_points"], list)
    assert isinstance(result["revision_advice"], list)
    assert isinstance(result["public_opinion_suggestions"], list)
    assert isinstance(result["integrated_revision_tasks"], list)
    assert rag_info["enabled"] is False
    assert rag_info["hit"] is False
    assert rag_info["sources"] == []
    assert rag_info["count"] == 0
    assert rag_info["gate"] == {}
    assert rag_info["retrieval_skipped"] is False
    assert rag_info["retrieval_executed"] is False


def test_legal_agent_gate_skip_does_not_call_retriever(monkeypatch):
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(False))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("retriever should not be called when gate rejects RAG")

    monkeypatch.setattr(legal_agent, "retrieve", fail_if_called)

    context = legal_agent._retrieve_legal_context(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert context == ""
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is False
    assert rag_info["sources"] == []
    assert rag_info["scores"] == []
    assert rag_info["rerank_scores"] == []
    assert rag_info["count"] == 0
    assert rag_info["fallback_used"] is False
    assert rag_info["gate"]["need_rag"] is False
    assert rag_info["retrieval_skipped"] is True
    assert rag_info["retrieval_executed"] is False
    assert rag_info["retrieval_status"] == "skipped_by_gate"


def test_legal_agent_gate_allows_retriever_once_and_records_hit(monkeypatch):
    call_count = {"retrieve": 0}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))

    def fake_retrieve(query, top_k=3):
        call_count["retrieve"] += 1
        return {
            "context": "[legal_risk_rules.md]\ncontext",
            "sources": [{"source": "legal_risk_rules.md", "score": 0.9, "retrieval_type": "hybrid"}],
            "chunks": [
                {
                    "chunk_id": "legal-1",
                    "source": "legal_risk_rules.md",
                    "title": "Legal Rules",
                    "score": 0.9,
                    "rerank_score": 0.95,
                    "metadata": {"retrieval_type": "hybrid", "rerank_enabled": True},
                    "text": "context",
                }
            ],
        }

    monkeypatch.setattr(legal_agent, "retrieve", fake_retrieve)

    context = legal_agent._retrieve_legal_context(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert call_count["retrieve"] == 1
    assert context == "[legal_risk_rules.md]\ncontext"
    assert rag_info["hit"] is True
    assert rag_info["sources"] == ["legal_risk_rules.md"]
    assert rag_info["scores"] == [0.9]
    assert rag_info["rerank_scores"] == [0.95]
    assert rag_info["gate"]["need_rag"] is True
    assert rag_info["retrieval_skipped"] is False
    assert rag_info["retrieval_executed"] is True
    assert rag_info["retrieval_status"] == "executed_with_hits"


def test_legal_agent_gate_allowed_empty_retrieval_is_distinct_from_gate_skip(monkeypatch):
    call_count = {"retrieve": 0}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))

    def fake_retrieve(query, top_k=3):
        call_count["retrieve"] += 1
        return {"context": "", "sources": [], "chunks": []}

    monkeypatch.setattr(legal_agent, "retrieve", fake_retrieve)

    context = legal_agent._retrieve_legal_context(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert call_count["retrieve"] == 1
    assert context == ""
    assert rag_info["hit"] is False
    assert rag_info["sources"] == []
    assert rag_info["gate"]["need_rag"] is True
    assert rag_info["retrieval_skipped"] is False
    assert rag_info["retrieval_executed"] is True
    assert rag_info["retrieval_status"] == "executed_no_hit"


def test_legal_agent_llm_gate_skip_continues_with_empty_context(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(False))
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: (_ for _ in ()).throw(AssertionError("retriever should be skipped")),
    )

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "legal_risks": ["risk"],
          "safe_points": ["safe"],
          "revision_advice": ["advice"],
          "public_opinion_suggestions": ["suggestion"],
          "integrated_revision_tasks": ["task"],
          "legal_safety_score_hint": 8,
          "review_summary": "summary"
        }
        """

    monkeypatch.setattr(legal_agent, "call_llm", fake_call_llm)

    result = legal_agent.run(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert "legal_context:" in captured_prompt["value"]
    assert result["legal_risks"] == ["risk"]
    assert rag_info["gate"]["need_rag"] is False
    assert rag_info["retrieval_skipped"] is True
    assert rag_info["retrieval_executed"] is False


def test_legal_agent_llm_mode_injects_legal_context_into_prompt(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))

    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[legal_risk_rules.md]\n避免提前定责，使用条件式责任表达。",
            "sources": [{"source": "legal_risk_rules.md", "score": 1.0}],
        },
    )

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        ```json
        {
          "legal_risks": ["避免提前认定全部事实。"],
          "safe_points": ["保留了配合监管的表述。"],
          "revision_advice": ["责任表述应加上调查结果前提。"],
          "public_opinion_suggestions": ["更明确回应消费者担忧。"],
          "integrated_revision_tasks": ["补充核查范围并避免绝对化表述。"],
          "legal_safety_score_hint": 8,
          "review_summary": "已参考提供的合规知识。"
        }
        ```
        """

    monkeypatch.setattr(legal_agent, "call_llm", fake_call_llm)

    result = legal_agent.run(TEST_PAYLOAD)

    assert "避免提前定责，使用条件式责任表达。" in captured_prompt["value"]
    assert result["legal_risks"] == ["避免提前认定全部事实。"]
    assert result["review_summary"] == "已参考提供的合规知识。"


def test_legal_agent_rag_failure_continues_llm(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))

    def failing_retrieve(query, top_k=3):
        raise RuntimeError("rag unavailable")

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "legal_risks": ["知识不足时保持审慎。"],
          "safe_points": ["未直接承认事实。"],
          "revision_advice": ["继续使用条件式表达。"],
          "public_opinion_suggestions": ["回应公众担忧。"],
          "integrated_revision_tasks": ["补充核查动作。"],
          "legal_safety_score_hint": 8,
          "review_summary": "RAG不可用，基于当前输入进行保守审查。"
        }
        """

    monkeypatch.setattr(legal_agent, "retrieve", failing_retrieve)
    monkeypatch.setattr(legal_agent, "call_llm", fake_call_llm)

    result = legal_agent.run(TEST_PAYLOAD)

    assert "legal_context:" in captured_prompt["value"]
    assert result["legal_risks"] == ["知识不足时保持审慎。"]
    assert result["review_summary"] == "RAG不可用，基于当前输入进行保守审查。"


def test_legal_agent_llm_failure_still_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[legal_risk_rules.md]\n避免提前定责。",
            "sources": [{"source": "legal_risk_rules.md", "score": 1.0}],
        },
    )
    monkeypatch.setattr(legal_agent, "call_llm", lambda prompt: '{"legal_risks": ["only one field"]}')

    result = legal_agent.run(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert set(result.keys()) >= {
        "legal_risks",
        "safe_points",
        "revision_advice",
        "public_opinion_suggestions",
        "integrated_revision_tasks",
        "legal_safety_score_hint",
        "review_summary",
    }
    assert isinstance(result["legal_risks"], list)
    assert isinstance(result["safe_points"], list)
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is True
    assert rag_info["sources"] == ["legal_risk_rules.md"]
    assert rag_info["count"] == 1


def test_legal_agent_records_rag_info_on_llm_success(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "[food_safety.md]\ncontext",
            "sources": [
                {"source": "food_safety.md", "score": 1.0},
                {"source": "legal_risk_rules.md", "score": 0.8},
            ],
        },
    )
    monkeypatch.setattr(
        legal_agent,
        "call_llm",
        lambda prompt: """
        {
          "legal_risks": ["risk"],
          "safe_points": ["safe"],
          "revision_advice": ["advice"],
          "public_opinion_suggestions": ["suggestion"],
          "integrated_revision_tasks": ["task"],
          "legal_safety_score_hint": 8,
          "review_summary": "summary"
        }
        """,
    )

    legal_agent.run(TEST_PAYLOAD)

    rag_info = legal_agent.get_last_rag_info()
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is True
    assert rag_info["sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert rag_info["count"] == 2


def test_legal_agent_records_rag_miss_when_retriever_fails(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: (_ for _ in ()).throw(RuntimeError("rag unavailable")),
    )
    monkeypatch.setattr(
        legal_agent,
        "call_llm",
        lambda prompt: """
        {
          "legal_risks": ["risk"],
          "safe_points": ["safe"],
          "revision_advice": ["advice"],
          "public_opinion_suggestions": ["suggestion"],
          "integrated_revision_tasks": ["task"],
          "legal_safety_score_hint": 8,
          "review_summary": "summary"
        }
        """,
    )

    legal_agent.run(TEST_PAYLOAD)

    rag_info = legal_agent.get_last_rag_info()
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is False
    assert rag_info["sources"] == []
    assert rag_info["count"] == 0
    assert rag_info["fallback_used"] is True
    assert rag_info["retrieval_status"] == "retrieval_error"


def test_legal_agent_continues_with_empty_legal_context_when_rag_returns_no_results(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_config.cache_clear()

    captured_prompt = {}
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: _gate_result(True))
    monkeypatch.setattr(
        legal_agent,
        "retrieve",
        lambda query, top_k=3: {
            "context": "",
            "chunks": [],
            "sources": [],
        },
    )

    def fake_call_llm(prompt):
        captured_prompt["value"] = prompt
        return """
        {
          "legal_risks": ["risk"],
          "safe_points": ["safe"],
          "revision_advice": ["advice"],
          "public_opinion_suggestions": ["suggestion"],
          "integrated_revision_tasks": ["task"],
          "legal_safety_score_hint": 8,
          "review_summary": "summary"
        }
        """

    monkeypatch.setattr(legal_agent, "call_llm", fake_call_llm)

    result = legal_agent.run(TEST_PAYLOAD)
    rag_info = legal_agent.get_last_rag_info()

    assert "legal_context:" in captured_prompt["value"]
    assert result["legal_risks"] == ["risk"]
    assert rag_info["enabled"] is True
    assert rag_info["hit"] is False
    assert rag_info["sources"] == []
    assert rag_info["chunks"] == []
    assert rag_info["count"] == 0
