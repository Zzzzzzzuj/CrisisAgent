from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp.legal_search_service import search_law as search_law_service


OPTIONAL_DEPENDENCY_MESSAGE = (
    "MCP SDK is not installed. Install optional dependencies with: "
    "pip install -r requirements-mcp.txt"
)


def create_server() -> Any:
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - depends on optional package.
        raise RuntimeError(OPTIONAL_DEPENDENCY_MESSAGE) from exc

    mcp = MCPServer("CrisisAgent Legal RAG")

    @mcp.tool()
    def search_law(
        query: str,
        top_k: int = 3,
        expected_source_category: str | None = None,
    ) -> dict[str, Any]:
        """Search CrisisAgent Legal RAG and return evidence with quality metadata."""

        return search_law_service(
            query=query,
            top_k=top_k,
            expected_source_category=expected_source_category,
        )

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the optional CrisisAgent Legal MCP server.")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = create_server()
    if args.transport == "streamable-http":
        server.run(transport="streamable-http", host=args.host, port=args.port)
        return
    server.run(transport="stdio")


try:
    mcp = create_server()
except RuntimeError:  # pragma: no cover - exercised when optional MCP SDK is absent.
    mcp = None


if __name__ == "__main__":
    main()
