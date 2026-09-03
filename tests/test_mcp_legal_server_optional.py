import importlib.util

import pytest

from backend.mcp import legal_mcp_server


def test_legal_mcp_server_module_imports_without_optional_sdk():
    assert legal_mcp_server.OPTIONAL_DEPENDENCY_MESSAGE


def test_create_server_reports_optional_dependency_when_mcp_missing():
    if importlib.util.find_spec("mcp") is not None:
        pytest.skip("MCP SDK is installed; missing dependency path is not applicable.")

    with pytest.raises(RuntimeError, match="requirements-mcp.txt"):
        legal_mcp_server.create_server()


def test_create_server_registers_search_law_tool_when_mcp_installed():
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional and not installed in the default test environment.")

    server = legal_mcp_server.create_server()

    assert server is not None
    assert hasattr(server, "tool")
