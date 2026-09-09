from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.tool_schemas import (
    ToolDefinitionResponse,
    ToolListResponse,
    ToolRunRequest,
    ToolRunResponse,
)
from backend.api.workspace_security import authorize, get_workspace_user, write_audit
from backend.mcp.schemas import MCP_SAFE_TOOL_NAMES
from backend.mcp.tools import call_mcp_tool, list_mcp_tools
from backend.skills.tool_runner import TOOL_POLICY_DENIED


router = APIRouter(prefix="/api/tools", tags=["safe-tools"])

_LIST_ROLES = {"admin", "operator", "legal_reviewer", "viewer"}
_RUN_ROLES = {
    "admin": set(MCP_SAFE_TOOL_NAMES),
    "operator": set(MCP_SAFE_TOOL_NAMES),
    "legal_reviewer": {"legal_rag_search", "guardrail_check"},
    "viewer": set(),
}


@router.get("", response_model=ToolListResponse)
def list_tools(user: dict = Depends(get_workspace_user)) -> ToolListResponse:
    authorize(user, _LIST_ROLES, "tool.list", "tool")
    tools = [_tool_definition(item) for item in list_mcp_tools() if item["name"] in MCP_SAFE_TOOL_NAMES]
    write_audit(user, "tool.list", "tool", "safe_allowlist", metadata={"count": len(tools)})
    return ToolListResponse(tools=tools, count=len(tools))


@router.post("/run", response_model=ToolRunResponse)
def run_tool(payload: ToolRunRequest, user: dict = Depends(get_workspace_user)) -> ToolRunResponse:
    tool_name = payload.tool_name
    metadata = {
        "tool_name": tool_name,
        "request_id": payload.request_id,
        "session_id": payload.session_id,
    }
    _ensure_safe_tool(tool_name, user, metadata)

    started_at = _now()
    tool_run_id = str(uuid4())
    if payload.dry_run:
        write_audit(user, "tool.run", "tool", tool_name, metadata={**metadata, "dry_run": True})
        return ToolRunResponse(
            tool_run_id=tool_run_id,
            tool_name=tool_name,
            status="success",
            output={"dry_run": True, "message": "Tool execution was not started."},
            trace={"tool_name": tool_name, "dry_run": True, "execution_path": "mcp_safe_adapter"},
            started_at=started_at,
            finished_at=_now(),
            request_id=payload.request_id,
            session_id=payload.session_id,
            dry_run=True,
        )

    try:
        envelope = call_mcp_tool(tool_name, payload.arguments, transport="http")
        result = envelope["tool_result"]
    except Exception as exc:
        write_audit(user, "tool.run.failed", "tool", tool_name, "failed", str(exc), metadata=metadata)
        return ToolRunResponse(
            tool_run_id=tool_run_id,
            tool_name=tool_name,
            status="failed",
            error_code="TOOL_EXECUTION_FAILED",
            error_message=str(exc),
            human_review_required=True,
            trace={"tool_name": tool_name, "execution_path": "mcp_safe_adapter", "error_code": "TOOL_EXECUTION_FAILED"},
            started_at=started_at,
            finished_at=_now(),
            request_id=payload.request_id,
            session_id=payload.session_id,
        )

    result_status = "success" if result.get("success") else "denied" if result.get("error_code") == TOOL_POLICY_DENIED else "failed"
    action = "tool.run" if result_status == "success" else "tool.run.denied" if result_status == "denied" else "tool.run.failed"
    write_audit(
        user,
        action,
        "tool",
        tool_name,
        result_status,
        str(result.get("error_message") or ""),
        metadata={
            **metadata,
            "error_code": result.get("error_code"),
            "human_review_required": bool(result.get("human_review_required", False)),
        },
    )
    return ToolRunResponse(
        tool_run_id=tool_run_id,
        tool_name=tool_name,
        status=result_status,
        output=result.get("output") or {},
        error_code=result.get("error_code"),
        error_message=result.get("error_message"),
        human_review_required=bool(result.get("human_review_required", False)),
        trace={**(result.get("trace") or {}), "execution_path": "mcp_safe_adapter"},
        started_at=started_at,
        finished_at=_now(),
        request_id=payload.request_id,
        session_id=payload.session_id,
    )


def _ensure_safe_tool(tool_name: str, user: dict, metadata: dict[str, Any]) -> None:
    if tool_name not in MCP_SAFE_TOOL_NAMES:
        write_audit(user, "tool.run.denied", "tool", tool_name, "denied", "not_in_safe_allowlist", metadata=metadata)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tool is not exposed by the safe allowlist.")
    allowed = _RUN_ROLES.get(str(user.get("role", "")), set())
    if tool_name not in allowed:
        write_audit(user, "tool.run.denied", "tool", tool_name, "denied", "insufficient_role", metadata=metadata)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for this tool.")


def _tool_definition(item: dict[str, Any]) -> ToolDefinitionResponse:
    return ToolDefinitionResponse(
        tool_name=item["name"],
        description=item["description"],
        input_schema=item["input_schema"],
        output_schema=item["output_schema"],
        risk_level=item["risk_level"],
        read_only=bool(item["read_only"]),
        requires_human_confirmation=bool(item["requires_human_confirmation"]),
        version=item["version"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
