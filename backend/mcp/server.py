from __future__ import annotations

import argparse
import sys
from typing import Any

from backend.mcp.tools import call_mcp_tool, list_mcp_tools


OPTIONAL_DEPENDENCY_MESSAGE = (
    "MCP SDK is not installed. Install optional dependencies with: "
    "pip install -r requirements-mcp.txt"
)


def create_server() -> Any:
    try:
        # MCP v2 renamed FastMCP to MCPServer. Keep a v1-compatible fallback
        # only for environments that still expose the older import path.
        try:
            from mcp.server.mcpserver import MCPServer
        except ImportError:
            from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError as exc:  # pragma: no cover - optional dependency.
        raise RuntimeError(OPTIONAL_DEPENDENCY_MESSAGE) from exc

    server = MCPServer("CrisisAgent Safe Tools")

    @server.tool()
    def legal_rag_search(
        query: str,
        top_k: int = 3,
        expected_source_category: str | None = None,
    ) -> dict[str, Any]:
        return call_mcp_tool(
            "legal_rag_search",
            {
                "query": query,
                "top_k": top_k,
                "expected_source_category": expected_source_category,
            },
        )

    @server.tool()
    def guardrail_check(event: str = "", statement: str = "") -> dict[str, Any]:
        return call_mcp_tool("guardrail_check", {"event": event, "statement": statement})

    @server.tool()
    def runtime_metrics_query() -> dict[str, Any]:
        return call_mcp_tool("runtime_metrics_query", {})

    @server.tool()
    def knowledge_document_search(source_category: str | None = None) -> dict[str, Any]:
        return call_mcp_tool(
            "knowledge_document_search",
            {"source_category": source_category},
        )

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CrisisAgent safe-tools MCP server.")
    parser.add_argument("--transport", choices=["stdio"], default="stdio")
    args = parser.parse_args()
    server = create_server()
    # Keep stdout reserved for MCP protocol traffic. Application logs belong on stderr.
    print("CrisisAgent MCP server starting on stdio", file=sys.stderr)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
