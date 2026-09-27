from __future__ import annotations

from typing import Any

from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


def create_runtime_skill_registry() -> SkillRegistry:
    return SkillRegistry([_triage(), _evidence_verification(), _context_retrieval(), _constraint_check()])


def _base(name: str, description: str, allowlist: tuple[str, ...], schema: dict[str, Any], output: dict[str, Any], handler) -> AgentSkill:
    return AgentSkill(name=name, skill_id=name, description=description, input_schema=schema, output_schema=output,
                      category="agent_skill", owner_agent="runtime", safety_level="high", enabled=True, version="1.0",
                      handler=handler, agent_allowlist=allowlist, preconditions=("offline_deterministic_input",),
                      read_only=True, risk_level="low")


def _triage() -> AgentSkill:
    return _base("event_risk_triage", "Classify risk labels, conflicts and priority for RedTeam.", ("redteam",),
        {"type": "object", "properties": {"event": {"type": "string"}, "risk_level": {"type": "string"}, "source_items": {"type": "array"}}, "required": ["event"], "additionalProperties": False},
        {"type": "object"}, lambda p: {"risk_level": p.get("risk_level", "unknown"), "risk_tags": ["source_conflict"] if _has_conflict(p.get("source_items", [])) else [], "priority": "high" if p.get("risk_level") == "high" else "normal", "source_conflict": _has_conflict(p.get("source_items", []))})


def _evidence_verification() -> AgentSkill:
    return _base("evidence_verification", "Summarize evidence confidence and source conflicts for Legal.", ("legal",),
        {"type": "object", "properties": {"evidence": {"type": "array"}, "fact_status": {"type": "string"}}, "required": [], "additionalProperties": False},
        {"type": "object"}, lambda p: {"evidence_count": len(p.get("evidence", [])), "fact_status": p.get("fact_status", ""), "low_confidence": any(float(i.get("score", 1)) < 0.1 for i in p.get("evidence", []) if isinstance(i, dict)), "source_conflict": p.get("fact_status") == "conflicting"})


def _context_retrieval() -> AgentSkill:
    return _base("context_retrieval", "Reuse the role-specific ContextPack built by the runtime provider.", ("writer", "legal"),
        {"type": "object", "properties": {"context_pack": {"type": "object"}}, "required": ["context_pack"], "additionalProperties": False},
        {"type": "object"}, lambda p: {"context_pack": p["context_pack"], "reused": True})


def _constraint_check() -> AgentSkill:
    return _base("statement_constraint_check", "Check statement constraints before Writer V2.", ("writer_v2",),
        {"type": "object", "properties": {"statement": {"type": "string"}, "fact_status": {"type": "string"}, "legal_review": {"type": "object"}}, "required": ["statement"], "additionalProperties": False},
        {"type": "object"}, lambda p: {"safe": p.get("fact_status") != "conflicting", "unverified_fact": p.get("fact_status") == "unverified", "legal_risk_count": len((p.get("legal_review") or {}).get("legal_risks", []))})


def _has_conflict(items: list[Any]) -> bool:
    return len({str(item.get("source", "")) for item in items if isinstance(item, dict)}) > 1
