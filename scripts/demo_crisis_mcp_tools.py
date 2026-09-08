from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp.tools import call_mcp_tool, list_mcp_tools


def main() -> int:
    # The demo is intentionally offline and must not inherit a postgres/LLM setup.
    os.environ["AGENT_MODE"] = "mock"
    os.environ["CHECKPOINT_STORAGE"] = "json"
    os.environ["VECTOR_BACKEND"] = "json"
    os.environ["EMBEDDING_MODEL"] = "hash"
    report = {
        "safe_tools": [item["name"] for item in list_mcp_tools()],
        "guardrail_check": call_mcp_tool(
            "guardrail_check",
            {"event": "食品安全事件正在核查", "statement": "我们保证绝不会有任何问题。"},
        ),
        "runtime_metrics_query": call_mcp_tool("runtime_metrics_query", {}),
        "invalid_input": call_mcp_tool("guardrail_check", {"unknown": True}),
        "offline": True,
        "real_network": False,
        "real_llm": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
