from backend.skills.mcp_adapter import mock_mcp_call, skill_to_mcp_resource, skill_to_mcp_tool
from backend.skills.skill_schema import AgentSkill


def test_skill_maps_to_mcp_tool_spec_without_external_runtime():
    tool = skill_to_mcp_tool(_skill())

    assert tool.name == "legal_rag_search"
    assert tool.annotations["mcp_runtime"] == "mock"
    assert tool.annotations["owner_agent"] == "legal_agent"


def test_skill_maps_to_mcp_resource_spec():
    resource = skill_to_mcp_resource(_skill())

    assert resource.uri == "crisisagent://skills/legal_rag_search"
    assert resource.mime_type == "application/json"


def test_mock_mcp_call_returns_trace_and_does_not_contact_server():
    tool = skill_to_mcp_tool(_skill())

    result = mock_mcp_call(tool, {"query": "食品安全"})

    assert result.success is True
    assert result.trace["mcp_runtime"] == "mock"
    assert result.content[0]["json"]["mock"] is True
    assert "no external MCP server" in result.content[0]["json"]["note"]


def _skill() -> AgentSkill:
    return AgentSkill(
        name="legal_rag_search",
        description="Search Legal RAG evidence.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        output_schema={"type": "object"},
        category="rag",
        owner_agent="legal_agent",
        safety_level="medium",
        enabled=True,
        version="1.0",
    )
