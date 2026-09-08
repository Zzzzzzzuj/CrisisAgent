from __future__ import annotations

from typing import Any

from backend.skills.tool_runner import ToolResult


MCP_SAFE_TOOL_NAMES = frozenset(
    {
        "legal_rag_search",
        "guardrail_check",
        "runtime_metrics_query",
        "knowledge_document_search",
    }
)

MCP_FORBIDDEN_TOOL_NAMES = frozenset(
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
        "run_crisis_workflow_mock",
    }
)


def tool_result_envelope(result: ToolResult, *, transport: str = "stdio") -> dict[str, Any]:
    """Serialize a ToolResult without confusing tool failure with transport failure."""

    return {
        "mcp": {
            "transport": transport,
            "protocol_status": "success",
        },
        "tool_result": result.to_dict(),
    }
