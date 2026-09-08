from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from backend.auth import ROLE_ADMIN, VALID_ROLES, get_current_user, is_auth_enabled
from backend.api.audit_store import get_audit_store


def get_workspace_user(
    current_user: Annotated[dict | None, Depends(get_current_user)],
    user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict:
    if is_auth_enabled():
        return current_user or {}
    role = user_role if user_role in VALID_ROLES else ROLE_ADMIN
    return {"id": user_id or "demo-system", "username": user_id or "demo-system", "role": role}


def authorize(user: dict, allowed_roles: set[str], action: str, resource_type: str, resource_id: str = "") -> None:
    if user.get("role") in allowed_roles:
        return
    write_audit(user, action, resource_type, resource_id, "denied", "insufficient_role")
    raise HTTPException(status_code=403, detail="Insufficient role for this action.")


def write_audit(user: dict, action: str, resource_type: str, resource_id: str, result: str = "success", reason: str = "", metadata: dict | None = None) -> None:
    get_audit_store().append({
        "actor_id": str(user.get("id", "demo-system")), "actor_role": str(user.get("role", "admin")),
        "action": action, "resource_type": resource_type, "resource_id": resource_id,
        "result": result, "reason": reason, "metadata": metadata or {},
    })


def owner_fields(user: dict, *, updating: bool = False) -> dict:
    value = str(user.get("id", "demo-system"))
    return {"updated_by": value} if updating else {"created_by": value, "updated_by": value, "owner_id": value}
