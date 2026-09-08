"""Optional MCP adapters for exposing CrisisAgent capabilities as tools."""
from backend.mcp.schemas import MCP_SAFE_TOOL_NAMES
from backend.mcp.tools import call_mcp_tool, create_mcp_registry, list_mcp_tools

__all__ = [
    "MCP_SAFE_TOOL_NAMES",
    "call_mcp_tool",
    "create_mcp_registry",
    "list_mcp_tools",
]
