from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from typing import Any, Callable

from backend.mcp.legal_search_service import search_law
from backend.mcp.schemas import MCP_SAFE_TOOL_NAMES, tool_result_envelope
from backend.skills.builtins import create_default_registry
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill
from backend.skills.tool_runner import TOOL_POLICY_DENIED, ToolResult, ToolRunner


def create_mcp_registry() -> SkillRegistry:
    """Build the external MCP allowlist from the internal Skill Registry."""

    internal = create_default_registry()
    selected: list[AgentSkill] = []
    for name in MCP_SAFE_TOOL_NAMES:
        skill = internal.get(name)
        if not skill.enabled or not skill.read_only or skill.requires_human_confirmation:
            continue
        handler = _mcp_handler(name, skill.handler)
        input_schema = deepcopy(skill.input_schema)
        if name == "legal_rag_search":
            input_schema.setdefault("properties", {})["expected_source_category"] = {
                "type": "string"
            }
        selected.append(replace(skill, input_schema=input_schema, handler=handler))
    return SkillRegistry(selected)


def list_mcp_tools(registry: SkillRegistry | None = None) -> list[dict[str, Any]]:
    registry = registry or create_mcp_registry()
    return registry.list_skills()


def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    registry: SkillRegistry | None = None,
    runner: ToolRunner | None = None,
    transport: str = "stdio",
) -> dict[str, Any]:
    registry = registry or create_mcp_registry()
    if tool_name not in MCP_SAFE_TOOL_NAMES or tool_name not in {
        item["name"] for item in registry.list_skills(include_disabled=True)
    }:
        result = ToolResult(
            tool_name=tool_name,
            success=False,
            error_code=TOOL_POLICY_DENIED,
            error_message="Tool is not exposed by the MCP safety allowlist.",
            human_review_required=True,
            trace={"tool_name": tool_name, "status": "blocked_by_mcp_allowlist"},
        )
        return tool_result_envelope(result, transport=transport)

    active_runner = runner or ToolRunner(registry)
    result = active_runner.run(tool_name, arguments)
    result = _promote_business_safety_signals(result)
    return tool_result_envelope(result, transport=transport)


def _mcp_handler(name: str, handler: Callable[[dict[str, Any]], dict[str, Any]] | None):
    if name == "legal_rag_search":
        return _search_law_handler
    if name == "knowledge_document_search":
        return _published_knowledge_handler
    return handler


def _search_law_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Reuse the existing RAG service; MCP never enables live-fetch."""

    return search_law(
        query=payload["query"],
        top_k=int(payload.get("top_k", 3)),
        expected_source_category=payload.get("expected_source_category"),
    )


def _published_knowledge_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Force the existing repository path to published documents only."""

    internal = create_default_registry().get("knowledge_document_search")
    if internal.handler is None:
        raise RuntimeError("knowledge_document_search handler is missing")
    return internal.handler(
        {
            "source_category": payload.get("source_category"),
            "published_only": True,
        }
    )


def _promote_business_safety_signals(result: ToolResult) -> ToolResult:
    """Keep domain safety signals visible beside generic ToolRunner status."""

    output = result.output if isinstance(result.output, dict) else {}
    evidence_quality = output.get("evidence_quality")
    human_review_required = result.human_review_required
    if isinstance(evidence_quality, dict):
        human_review_required = human_review_required or bool(
            evidence_quality.get("should_trigger_human_review")
        )
    if output.get("hit") is True:
        human_review_required = True

    fallback_used = result.fallback_used or bool(output.get("fallback_used"))
    if human_review_required == result.human_review_required and fallback_used == result.fallback_used:
        return result
    trace = dict(result.trace)
    trace["fallback_used"] = fallback_used
    trace["human_review_required"] = human_review_required
    return replace(
        result,
        fallback_used=fallback_used,
        human_review_required=human_review_required,
        trace=trace,
    )
