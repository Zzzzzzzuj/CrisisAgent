from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.harness_comparison_schemas import HarnessComparisonCreateRequest, HarnessComparisonListResponse
from backend.api.workspace_security import authorize, get_workspace_user, write_audit
from backend.evaluation.harness_comparison import compare_harness_ids, render_comparison_markdown
from backend.evaluation.harness_comparison_store import get_harness_comparison_store


router = APIRouter(prefix="/api/harness-comparisons", tags=["harness-comparison"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_comparison(payload: HarnessComparisonCreateRequest, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator"}, "harness_comparison.create", "harness_comparison")
    try:
        comparison = compare_harness_ids(
            payload.baseline_harness_id,
            payload.baseline_version,
            payload.candidate_harness_id,
            payload.candidate_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_harness_comparison_store().save(comparison)
    write_audit(user, "harness_comparison.create", "harness_comparison", comparison["comparison_id"])
    return comparison


@router.get("", response_model=HarnessComparisonListResponse)
def list_comparisons(user: dict = Depends(get_workspace_user)) -> HarnessComparisonListResponse:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness_comparison.list", "harness_comparison")
    items = get_harness_comparison_store().list()
    return HarnessComparisonListResponse(comparisons=items, count=len(items))


@router.get("/{comparison_id}")
def get_comparison(comparison_id: str, format: str = Query(default="json"), user: dict = Depends(get_workspace_user)) -> dict | str:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness_comparison.view", "harness_comparison", comparison_id)
    item = get_harness_comparison_store().get(comparison_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Harness comparison '{comparison_id}' not found.")
    if format == "markdown":
        return render_comparison_markdown(item)
    if format != "json":
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'.")
    return item
