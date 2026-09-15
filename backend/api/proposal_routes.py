from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.proposal_schemas import ProposalCreateRequest, ProposalReviewRequest
from backend.api.workspace_security import authorize, get_workspace_user, write_audit
from backend.evaluation.harness_comparison import compare_harnesses, evaluate_comparison_gate
from backend.evaluation.harness_comparison_store import get_harness_comparison_store
from backend.harness.proposal import build_proposal, validate_allowed_patch
from backend.harness.proposal_store import get_harness_proposal_store
from backend.harness.service import copy_harness_version, get_effective_harness_spec, mark_harness_evaluated, update_candidate_harness
from backend.harness.spec import spec_hash

router = APIRouter(prefix="/api/harness-proposals", tags=["harness-proposal"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_proposal(payload: ProposalCreateRequest, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator"}, "harness_proposal.create", "harness_proposal")
    try:
        baseline = get_effective_harness_spec(payload.baseline_harness_id, payload.baseline_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    proposal = build_proposal(payload.diagnosis, baseline, source_run_id=payload.source_run_id, comparison_id=payload.comparison_id, replay_case_id=payload.replay_case_id)
    get_harness_proposal_store().save(proposal)
    write_audit(user, "harness_proposal.create", "harness_proposal", proposal["proposal_id"])
    return proposal


@router.get("")
def list_proposals(user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness_proposal.list", "harness_proposal")
    values = get_harness_proposal_store().list()
    return {"proposals": list(reversed(values)), "count": len(values)}


@router.get("/{proposal_id}")
def get_proposal(proposal_id: str, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "harness_proposal.view", "harness_proposal", proposal_id)
    proposal = get_harness_proposal_store().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return proposal


@router.post("/{proposal_id}/accept")
def accept_proposal(proposal_id: str, payload: ProposalReviewRequest, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin"}, "harness_proposal.accept", "harness_proposal", proposal_id)
    proposal = _get(proposal_id)
    old_status = proposal.get("status")
    if old_status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT proposals can be accepted.")
    proposal.update({"status": "ACCEPTED", "reviewer": str(user.get("id", "")), "review_reason": payload.reason})
    get_harness_proposal_store().replace(proposal)
    write_audit(user, "harness_proposal.accept", "harness_proposal", proposal_id, metadata={"old_status": old_status, "new_status": "ACCEPTED", "reason": payload.reason})
    return proposal


@router.post("/{proposal_id}/reject")
def reject_proposal(proposal_id: str, payload: ProposalReviewRequest, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin"}, "harness_proposal.reject", "harness_proposal", proposal_id)
    proposal = _get(proposal_id)
    old_status = proposal.get("status")
    if old_status not in {"DRAFT", "ACCEPTED"}:
        raise HTTPException(status_code=409, detail="Only DRAFT or ACCEPTED proposals can be rejected.")
    proposal.update({"status": "REJECTED", "reviewer": str(user.get("id", "")), "review_reason": payload.reason})
    get_harness_proposal_store().replace(proposal)
    write_audit(user, "harness_proposal.reject", "harness_proposal", proposal_id, metadata={"old_status": old_status, "new_status": "REJECTED", "reason": payload.reason})
    return proposal


@router.post("/{proposal_id}/apply")
def apply_proposal(proposal_id: str, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin"}, "harness_proposal.apply", "harness_proposal", proposal_id)
    proposal = _get(proposal_id)
    if proposal.get("status") != "ACCEPTED":
        raise HTTPException(status_code=409, detail="Only ACCEPTED proposals can be applied.")
    validate_allowed_patch(proposal.get("allowed_patch", {}))
    baseline = get_effective_harness_spec(proposal["baseline_harness_id"], proposal["baseline_version"])
    current_hash = spec_hash(baseline)
    if current_hash != proposal.get("spec_hash"):
        raise HTTPException(status_code=409, detail="Baseline HarnessSpec changed since proposal creation; recreate proposal.")
    candidate = copy_harness_version(proposal["baseline_harness_id"], proposal["baseline_version"], f"proposal-{proposal_id[-8:]}")
    candidate_id = candidate["metadata"]["harness_id"]
    updated = update_candidate_harness(candidate_id, candidate["metadata"]["version"], proposal["allowed_patch"], f"Applied {proposal_id}: {proposal['rationale']}")
    comparison = compare_harnesses(baseline, updated)
    comparison["gate_result"] = evaluate_comparison_gate(comparison)
    get_harness_comparison_store().save(comparison)
    evaluated = mark_harness_evaluated(candidate_id, candidate["metadata"]["version"], comparison["comparison_id"], comparison["gate_result"])
    proposal.update({"status": "APPLIED", "applied_harness_id": candidate_id, "applied_version": candidate["metadata"]["version"], "comparison_id": comparison["comparison_id"]})
    get_harness_proposal_store().replace(proposal)
    write_audit(user, "harness_proposal.apply", "harness_proposal", proposal_id, metadata={"old_status": "ACCEPTED", "new_status": "APPLIED", "proposal_id": proposal_id, "baseline_harness_id": proposal["baseline_harness_id"], "baseline_version": proposal["baseline_version"], "baseline_spec_hash": proposal.get("spec_hash"), "candidate_harness_id": candidate_id, "candidate_version": candidate["metadata"]["version"], "comparison_id": comparison["comparison_id"]})
    return {"proposal": proposal, "candidate": evaluated, "comparison": comparison}


def _get(proposal_id: str) -> dict:
    proposal = get_harness_proposal_store().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return proposal
