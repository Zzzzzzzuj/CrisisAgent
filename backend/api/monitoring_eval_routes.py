from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from backend.api.monitoring_eval import load_monitoring_eval_cases, run_monitoring_eval
from backend.api.workspace_security import authorize, get_workspace_user

router = APIRouter(prefix="/api/monitoring-eval", tags=["monitoring-eval"])
CASES_PATH = Path(__file__).resolve().parents[2] / "data" / "monitoring_eval_cases.json"


@router.get("")
def monitoring_eval(user: dict = Depends(get_workspace_user)):
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "monitoring_eval.view", "monitoring_eval")
    return run_monitoring_eval(load_monitoring_eval_cases(CASES_PATH))
