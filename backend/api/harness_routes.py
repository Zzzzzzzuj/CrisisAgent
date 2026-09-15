from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.harness_schemas import HarnessApproveRequest, HarnessCandidatePatchRequest, HarnessCopyRequest, HarnessCreateRequest, HarnessEvaluateRequest, HarnessListResponse, HarnessRejectRequest, HarnessSpecResponse
from backend.api.workspace_security import authorize, get_workspace_user, write_audit
from backend.evaluation.harness_comparison import compare_harness_ids, evaluate_comparison_gate
from backend.evaluation.harness_comparison_store import get_harness_comparison_store
from backend.harness.spec import spec_hash
from backend.harness.service import approve_harness_version, copy_harness_version, create_harness_version, enable_approved_harness_version, get_effective_harness_spec, list_harness_versions, mark_harness_evaluated, reject_harness_version, rollback_harness_version, update_candidate_harness


router = APIRouter(prefix="/api/harnesses", tags=["harness-spec"])


@router.get("", response_model=HarnessListResponse)
def list_harnesses(user: dict = Depends(get_workspace_user)) -> HarnessListResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness.list", "harness")
    items = list_harness_versions()
    return HarnessListResponse(harnesses=items, count=len(items))


@router.get("/{harness_id}/{version}", response_model=HarnessSpecResponse)
def get_harness(harness_id: str, version: str, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness.view", "harness", harness_id)
    try:
        return HarnessSpecResponse(**get_effective_harness_spec(harness_id, version))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=HarnessSpecResponse, status_code=status.HTTP_201_CREATED)
def create_harness(payload: HarnessCreateRequest, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.create", "harness")
    try:
        result = create_harness_version(payload.spec, payload.parent_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(user, "harness.create", "harness", result["metadata"]["harness_id"])
    return HarnessSpecResponse(**result)


@router.post("/{harness_id}/{version}/copy", response_model=HarnessSpecResponse, status_code=status.HTTP_201_CREATED)
def copy_harness(harness_id: str, version: str, payload: HarnessCopyRequest, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.copy", "harness", harness_id)
    try:
        result = copy_harness_version(harness_id, version, payload.new_version)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    write_audit(user, "harness.copy", "harness", harness_id)
    return HarnessSpecResponse(**result)


@router.post("/{harness_id}/{version}/enable", response_model=HarnessSpecResponse)
def enable_harness(harness_id: str, version: str, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.enable", "harness", harness_id)
    try:
        result = enable_approved_harness_version(harness_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(user, "harness.enable", "harness", harness_id, metadata={"old_status": "APPROVED_OR_ACTIVE", "new_status": result["metadata"].get("status"), "version": version, "spec_hash": spec_hash(result)})
    return HarnessSpecResponse(**result)


@router.post("/{harness_id}/{version}/rollback", response_model=HarnessSpecResponse)
def rollback_harness(harness_id: str, version: str, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.rollback", "harness", harness_id)
    before_active = next((item for item in list_harness_versions() if item.get("metadata", {}).get("status") in {"active", "ACTIVE"}), None)
    try:
        result = rollback_harness_version(harness_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(user, "harness.rollback", "harness", harness_id, metadata={"old_status": (before_active or {}).get("metadata", {}).get("status"), "new_status": result["metadata"].get("status"), "restored_version": version, "previous_active_version": (before_active or {}).get("metadata", {}).get("version"), "spec_hash": spec_hash(result)})
    return HarnessSpecResponse(**result)


@router.patch("/{harness_id}/{version}/candidate", response_model=HarnessSpecResponse)
def patch_candidate(harness_id: str, version: str, payload: HarnessCandidatePatchRequest, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.candidate.update", "harness", harness_id)
    try:
        result = update_candidate_harness(harness_id, version, payload.changes, payload.change_summary)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(user, "harness.candidate.update", "harness", harness_id)
    return HarnessSpecResponse(**result)


@router.post("/{harness_id}/{version}/evaluate")
def evaluate_candidate(harness_id: str, version: str, payload: HarnessEvaluateRequest, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator"}, "harness.evaluate", "harness", harness_id)
    try:
        comparison = compare_harness_ids(payload.baseline_harness_id, payload.baseline_version, harness_id, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    comparison["gate_result"] = evaluate_comparison_gate(comparison)
    get_harness_comparison_store().save(comparison)
    try:
        result = mark_harness_evaluated(harness_id, version, comparison["comparison_id"], comparison["gate_result"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(user, "harness.evaluate", "harness", harness_id, metadata={"comparison_id": comparison["comparison_id"], "passed": comparison["gate_result"]["passed"]})
    return {"harness": result, "comparison": comparison}


@router.post("/{harness_id}/{version}/approve", response_model=HarnessSpecResponse)
def approve_candidate(harness_id: str, version: str, payload: HarnessApproveRequest, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.approve", "harness", harness_id)
    comparison = get_harness_comparison_store().get(payload.comparison_id)
    if comparison is None or comparison.get("candidate", {}).get("harness_id") != harness_id or comparison.get("candidate", {}).get("version") != version:
        raise HTTPException(status_code=404, detail="Comparison for candidate not found.")
    gate = comparison.get("gate_result") or evaluate_comparison_gate(comparison)
    if not gate.get("passed"):
        raise HTTPException(status_code=409, detail="Candidate failed evaluation gates.")
    try:
        result = approve_harness_version(harness_id, version, payload.comparison_id, str(user.get("id", "")), {**gate, "reason": payload.reason})
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(user, "harness.approve", "harness", harness_id, metadata={"old_status": "EVALUATED", "new_status": result["metadata"].get("status"), "comparison_id": payload.comparison_id, "reason": payload.reason, "version": version, "spec_hash": spec_hash(result)})
    return HarnessSpecResponse(**result)


@router.post("/{harness_id}/{version}/reject", response_model=HarnessSpecResponse)
def reject_candidate(harness_id: str, version: str, payload: HarnessRejectRequest, user: dict = Depends(get_workspace_user)) -> HarnessSpecResponse:
    authorize(user, {"admin"}, "harness.reject", "harness", harness_id)
    try:
        result = reject_harness_version(harness_id, version, str(user.get("id", "")), payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(user, "harness.reject", "harness", harness_id, metadata={"reason": payload.reason})
    return HarnessSpecResponse(**result)
