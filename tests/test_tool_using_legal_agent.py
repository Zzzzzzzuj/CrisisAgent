from backend.agents.tool_using_legal_agent import run
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


def test_tool_using_legal_agent_high_risk_calls_required_tools():
    result = run(
        {
            "event": "某食品品牌被曝光使用过期原料，消费者要求监管介入。",
            "sentiment_result": {"risk_level": "high"},
            "redteam_result": {"issues": ["公众质疑"]},
        },
        registry=_registry(),
    )

    called_tools = [item["name"] for item in result["tool_call_trace"]]
    assert "legal_rag_search" in called_tools
    assert "guardrail_check" in called_tools
    assert result["human_review_required"] is True
    assert result["tool_plan"]["human_review_required"] is True
    assert result["tool_call_trace"][0]["policy"]["allow"] is True


def test_tool_using_legal_agent_low_risk_records_skip_reason():
    result = run(
        {
            "event": "用户反馈商品包装轻微破损，希望客服处理。",
            "sentiment_result": {"risk_level": "low"},
        },
        registry=_registry(),
    )

    assert "legal_rag_search" not in [item["name"] for item in result["tool_call_trace"]]
    assert result["tool_plan"]["skipped_tools"][0]["tool"] == "legal_rag_search"
    assert result["human_review_required"] is False


def test_tool_arguments_validation_failed_stops_execution():
    broken_registry = SkillRegistry(
        [
            AgentSkill(
                name="legal_rag_search",
                description="Broken schema",
                input_schema={
                    "type": "object",
                    "properties": {"required_extra": {"type": "string"}},
                    "required": ["required_extra"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                category="rag",
                owner_agent="legal_agent",
                safety_level="medium",
                enabled=True,
                version="test",
                handler=lambda payload: {"should_not_execute": True},
            ),
            _guardrail_skill(),
        ]
    )

    result = run(
        {
            "event": "某食品品牌被曝光使用过期原料，消费者要求监管介入。",
            "sentiment_result": {"risk_level": "high"},
        },
        registry=broken_registry,
    )

    assert result["tool_call_trace"][0]["success"] is False
    assert "schema_validation_failed" in result["tool_call_trace"][0]["error"]
    assert len(result["tool_call_trace"]) == 1


def test_mock_demo_path_returns_observations_and_metadata():
    result = run(
        {
            "event": "某APP出现用户信息异常可见，截图传播。",
            "sentiment_result": {"risk_level": "high"},
            "draft": "我们正在核查。",
        },
        registry=_registry(),
    )

    assert result["tool_observations"]
    assert result["legal_risks"]
    assert result["safe_points"]
    assert result["_metadata"]["tool_using_agent"]["observation_count"] >= 2


def _registry() -> SkillRegistry:
    return SkillRegistry([_rag_skill(), _guardrail_skill(), _knowledge_skill()])


def _rag_skill() -> AgentSkill:
    return AgentSkill(
        name="legal_rag_search",
        description="Test RAG",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="rag",
        owner_agent="legal_agent",
        safety_level="medium",
        enabled=True,
        version="test",
        handler=lambda payload: {
            "context": "legal context",
            "sources": [{"source": "food_safety.md"}],
            "chunks": [{"chunk_id": "c1", "text_preview": "核查批次"}],
            "fallback_used": False,
        },
    )


def _guardrail_skill() -> AgentSkill:
    return AgentSkill(
        name="guardrail_check",
        description="Test guardrail",
        input_schema={
            "type": "object",
            "properties": {"event": {"type": "string"}, "statement": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="safety",
        owner_agent="guardrails",
        safety_level="high",
        enabled=True,
        version="test",
        handler=lambda payload: {"input": {"hit": False}, "output": {"hit": False}, "hit": False},
    )


def _knowledge_skill() -> AgentSkill:
    return AgentSkill(
        name="knowledge_document_search",
        description="Test knowledge search",
        input_schema={
            "type": "object",
            "properties": {"source_category": {"type": "string"}, "published_only": {"type": "boolean"}},
            "required": [],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="knowledge",
        owner_agent="legal_agent",
        safety_level="low",
        enabled=True,
        version="test",
        handler=lambda payload: {"documents": [{"source_name": "food_safety.md"}], "count": 1},
    )
