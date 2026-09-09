from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.agents.context_pack import build_context_pack
from backend.api.alert_store import get_alert_store
from backend.api.case_memory_schemas import CaseMemoryResponse
from backend.api.case_memory_store import get_case_memory_store
from backend.api.collected_item_store import get_collected_item_store
from backend.api.context_pack_schemas import ContextPackBuildRequest, ContextPackBuildResponse
from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_store import get_crisis_event_store
from backend.api.workspace_security import authorize, get_workspace_user, write_audit


router = APIRouter(prefix="/api/context-pack", tags=["context-pack"])
BUILD_ROLES = {"admin", "operator", "legal_reviewer"}


@router.post("/build", response_model=ContextPackBuildResponse)
def build_pack(payload: ContextPackBuildRequest, user: dict = Depends(get_workspace_user)) -> ContextPackBuildResponse:
    authorize(user, BUILD_ROLES, "context_pack.build", "context_pack")
    if not payload.event_id and not payload.event_text:
        raise HTTPException(status_code=422, detail="event_id or event_text is required.")
    event = None
    if payload.event_id:
        event = get_crisis_event_store().get(payload.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"Crisis event '{payload.event_id}' not found.")
    signals = []
    alerts = []
    evidence = []
    review_notes = []
    if event:
        signals = get_collected_item_store().list_items(ingestion_run_id=event.get("source_run_id"), limit=50)
        alerts = [
            item for item in get_alert_store().list(limit=200)
            if item.get("related_event_id") == payload.event_id or item.get("entity_id") == event.get("entity_id")
        ]
        run = get_event_agent_run_store().get_latest(payload.event_id)
        if run:
            review_notes = [str(run.get("error", ""))] if run.get("error") else []
            for trace_item in run.get("trace", []) or []:
                if isinstance(trace_item, dict) and trace_item.get("agent") == "legal":
                    rag = trace_item.get("rag") or {}
                    evidence = rag.get("evidence_chunks") or rag.get("chunks") or []
                    break
    memories = []
    if payload.include_memories:
        memories = get_case_memory_store().list_memories(
            entity_id=payload.entity_id or (event or {}).get("entity_id"),
            limit=100,
        )
    pack = build_context_pack(
        event=event,
        event_text=payload.event_text,
        public_signals=signals,
        alerts=alerts,
        legal_evidence=evidence,
        case_memories=memories,
        human_review_notes=review_notes,
        token_budget_hint=payload.token_budget_hint,
        target_agent=payload.target_agent,
    )
    write_audit(user, "context_pack.build", "context_pack", payload.event_id or "")
    return ContextPackBuildResponse(
        context_pack=pack,
        memory_count=len(pack["related_case_memories"]),
        dropped_fields=pack["dropped_fields"],
        safety_notes=[
            "Deterministic preview only; no LLM call.",
            "Full news text, system prompts, API keys, and tool arguments are excluded.",
        ],
        agent_specific_focus=pack["agent_specific_focus"],
        selected_case_ids=pack["selected_case_ids"],
        latest_round_summary=pack["latest_round_summary"],
    )
