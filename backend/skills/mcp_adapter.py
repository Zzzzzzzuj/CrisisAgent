from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.skills.skill_schema import AgentSkill


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPResourceSpec:
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"


@dataclass(frozen=True)
class MCPCallResult:
    tool_name: str
    success: bool
    content: list[dict[str, Any]]
    error: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


def skill_to_mcp_tool(skill: AgentSkill) -> MCPToolSpec:
    return MCPToolSpec(
        name=skill.name,
        description=skill.description,
        input_schema=skill.input_schema,
        annotations={
            "category": skill.category,
            "owner_agent": skill.owner_agent,
            "safety_level": skill.safety_level,
            "version": skill.version,
            "enabled": skill.enabled,
            "mcp_runtime": "mock",
        },
    )


def skill_to_mcp_resource(skill: AgentSkill) -> MCPResourceSpec:
    return MCPResourceSpec(
        uri=f"crisisagent://skills/{skill.name}",
        name=skill.name,
        description=f"Skill metadata for {skill.name}",
    )


def mock_mcp_call(tool: MCPToolSpec, arguments: dict[str, Any]) -> MCPCallResult:
    if not tool.name:
        return MCPCallResult(
            tool_name="",
            success=False,
            content=[],
            error="missing_tool_name",
            trace={"mcp_runtime": "mock", "status": "failed"},
        )
    return MCPCallResult(
        tool_name=tool.name,
        success=True,
        content=[
            {
                "type": "json",
                "json": {
                    "tool": tool.name,
                    "arguments": arguments,
                    "mock": True,
                    "note": "MCP-compatible mock call; no external MCP server was contacted.",
                },
            }
        ],
        trace={
            "mcp_runtime": "mock",
            "status": "success",
            "called_at": datetime.now(timezone.utc).isoformat(),
        },
    )
