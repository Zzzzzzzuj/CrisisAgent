from __future__ import annotations

from backend.mcp.schemas import MCP_SAFE_TOOL_NAMES
from backend.mcp.tools import call_mcp_tool, create_mcp_registry, list_mcp_tools
from backend.skills.tool_runner import TOOL_INPUT_INVALID, ToolResult


def test_mcp_exposes_only_safe_read_only_tools():
    names = {item["name"] for item in list_mcp_tools()}
    assert names == set(MCP_SAFE_TOOL_NAMES)
    assert not names.intersection(
        {
            "approve",
            "reject",
            "publish",
            "final_publish",
            "send_notification",
            "delete_session",
            "modify_knowledge_base",
            "live_fetch",
            "run_crisis_workflow",
        }
    )


def test_mcp_calls_tool_runner_and_preserves_structured_result(monkeypatch):
    captured = {}

    class FakeRunner:
        def run(self, name, arguments):
            captured["name"] = name
            captured["arguments"] = arguments
            return ToolResult(
                tool_name=name,
                success=False,
                error_code=TOOL_INPUT_INVALID,
                error_message="invalid",
                human_review_required=True,
                trace={"attempts": 0},
            )

    result = call_mcp_tool(
        "guardrail_check",
        {"unknown": True},
        registry=create_mcp_registry(),
        runner=FakeRunner(),
    )
    assert captured["name"] == "guardrail_check"
    assert result["mcp"]["protocol_status"] == "success"
    assert result["tool_result"]["error_code"] == TOOL_INPUT_INVALID
    assert result["tool_result"]["human_review_required"] is True


def test_mcp_promotes_guardrail_hit_to_human_review():
    result = call_mcp_tool(
        "guardrail_check",
        {"statement": "我们保证绝不会有任何问题。"},
    )
    assert result["tool_result"]["success"] is True
    assert result["tool_result"]["output"]["hit"] is True
    assert result["tool_result"]["human_review_required"] is True


def test_mcp_blocks_sensitive_tool_with_structured_policy_error():
    result = call_mcp_tool("approve", {"session_id": "x"})
    assert result["mcp"]["protocol_status"] == "success"
    assert result["tool_result"]["success"] is False
    assert result["tool_result"]["human_review_required"] is True


def test_knowledge_search_forces_published_only(monkeypatch):
    registry = create_mcp_registry()

    class FakeRepository:
        def load_published_documents(self):
            return [{"source_category": "food_safety", "status": "published", "is_enabled": True}]

        def list_documents(self):
            raise AssertionError("MCP must not load draft or disabled documents")

    import backend.skills.builtins as builtins

    monkeypatch.setattr(builtins, "KnowledgeRepository", FakeRepository)
    handler = registry.get("knowledge_document_search").handler
    result = handler({"source_category": "food_safety", "published_only": False})
    assert result["count"] == 1
    assert result["documents"][0]["status"] == "published"
