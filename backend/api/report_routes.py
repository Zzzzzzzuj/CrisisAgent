from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_store import get_crisis_event_store
from backend.api.report_generator import build_crisis_report, render_markdown
from backend.api.report_schemas import MarkdownReportResponse
from backend.api.workspace_security import authorize, get_workspace_user, write_audit


router = APIRouter(prefix="/api/events", tags=["event-reports"])


@router.get("/{event_id}/report")
def get_event_report(
    event_id: str,
    format: str = Query(default="json"),
    user: dict = Depends(get_workspace_user),
):
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "report.view", "event", event_id)
    if format not in {"json", "markdown"}:
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'.")

    event = get_crisis_event_store().get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")
    run = get_event_agent_run_store().get_latest(event_id)
    if run is None:
        raise HTTPException(status_code=400, detail="Run the CrisisAgent before exporting a report.")

    report = build_crisis_report(event, run)
    write_audit(user, "report.view", "event", event_id)
    if format == "markdown":
        return MarkdownReportResponse(
            format="markdown",
            event_id=event_id,
            markdown_content=render_markdown(report),
            automatic_publish=False,
        )
    return report
