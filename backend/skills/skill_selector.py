from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.skills.runtime_skills import create_runtime_skill_registry
from backend.skills.tool_runner import ToolRunner

SKILL_PLAN = {
    "writer": [("context_retrieval", "Writer needs role-specific history and constraints.")],
    "redteam": [("event_risk_triage", "RedTeam needs deterministic risk/conflict triage.")],
    "legal": [("context_retrieval", "Legal needs role-specific evidence context."), ("evidence_verification", "Legal must verify evidence confidence and conflict.")],
    "writer_v2": [("statement_constraint_check", "Writer V2 must check statement constraints before revision.")],
    "decision": [],
}


class SkillSelector:
    def __init__(self, registry=None):
        self.registry = registry or create_runtime_skill_registry()

    def select_and_execute(self, state, agent_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        cached = (state.metadata.get("skill_runtime_results") or {}).get(agent_name)
        if isinstance(cached, dict):
            return deepcopy(cached)
        selected, skipped, results = [], [], []
        planned = SKILL_PLAN.get(agent_name, [])
        planned_names = {name for name, _ in planned}
        for skill_name, reason in planned:
            definition = self.registry.get(skill_name)
            if agent_name not in definition.agent_allowlist:
                skipped.append({"skill_id": skill_name, "reason": "agent_not_allowed"})
                continue
            runner = ToolRunner(self.registry, harness_spec=state.metadata.get("harness_spec") or {})
            result = runner.run(skill_name, self._arguments(skill_name, state, payload))
            item = result.to_dict()
            item.update({"reason": reason, "skill_id": definition.skill_id or skill_name})
            selected.append({"skill_id": skill_name, "reason": reason})
            results.append(item)
        for definition in self.registry.list_skills():
            skill_name = definition["name"]
            if skill_name not in planned_names:
                skipped.append({"skill_id": skill_name, "reason": "not_required_for_agent"})
        output = {"selected": selected, "skipped": skipped, "results": results, "failure_tags": self._failure_tags(results)}
        state.metadata.setdefault("skill_runtime_results", {})[agent_name] = deepcopy(output)
        state.metadata.setdefault("skill_selection", {})[agent_name] = {"selected": selected, "skipped": skipped}
        return output

    @staticmethod
    def _arguments(skill_name, state, payload):
        ingestion = state.metadata.get("ingestion") or {}
        pack = payload.get("context_pack") or {}
        if skill_name == "context_retrieval":
            return {"context_pack": pack}
        if skill_name == "event_risk_triage":
            return {"event": state.event, "risk_level": (state.get_result("sentiment") or {}).get("risk_level", ingestion.get("risk_level", "")), "source_items": ingestion.get("source_items", [])}
        if skill_name == "evidence_verification":
            return {"evidence": pack.get("top_legal_evidence", []), "fact_status": pack.get("fact_status", ingestion.get("fact_status", ""))}
        return {"statement": (payload.get("first_draft") or {}).get("statement", payload.get("statement", "")), "fact_status": ingestion.get("fact_status", ""), "legal_review": payload.get("legal_review", {})}

    @staticmethod
    def _failure_tags(results):
        return list(dict.fromkeys("skill_" + str(item.get("error_code") or "execution_failed").lower() for item in results if not item.get("success")))
