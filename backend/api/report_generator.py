from __future__ import annotations

import json
from typing import Any


def build_crisis_report(event: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    trace = run.get("trace") if isinstance(run.get("trace"), list) else []
    trace_summary = _build_trace_summary(trace)
    policy_triggers = _as_list(run.get("policy_triggers"))
    human_review_required = bool(run.get("human_review_required", False))

    return {
        "report_type": "crisis_event_report",
        "event": {
            "event_id": event.get("event_id", ""),
            "title": event.get("title", ""),
            "company": event.get("company", ""),
            "status": event.get("status", ""),
            "created_at": event.get("created_at", ""),
            "updated_at": event.get("updated_at", ""),
        },
        "sources": {
            "source_run_id": event.get("source_run_id", ""),
            "cluster_id": event.get("cluster_id", ""),
            "source_count": event.get("source_count", 0),
            "source_items": _as_list(event.get("source_items")),
            "first_published_at": event.get("first_published_at", ""),
            "last_published_at": event.get("last_published_at", ""),
            "event_fingerprint": event.get("event_fingerprint", ""),
        },
        "risk_and_fact": {
            "risk_level": event.get("risk_level", ""),
            "public_emotion": event.get("public_emotion", ""),
            "fact_status": event.get("fact_status", ""),
            "event_status": event.get("event_status", ""),
            "human_review_required": bool(event.get("human_review_required", False)),
        },
        "agent_run": {
            "agent_run_id": run.get("agent_run_id", ""),
            "session_id": run.get("session_id", ""),
            "run_status": run.get("status", ""),
            "mode": run.get("mode", ""),
            "started_at": run.get("started_at", ""),
            "finished_at": run.get("finished_at", ""),
            "scores": run.get("scores") if isinstance(run.get("scores"), dict) else {},
            "final_statement_preview": str(run.get("final_statement_preview", "")),
            "automatic_publish": False,
        },
        "trace": trace_summary,
        "human_review": {
            "human_review_required": human_review_required,
            "policy_triggers": policy_triggers,
            "review_reason": _review_reason(policy_triggers, human_review_required),
            "approval_status": _approval_status(run, human_review_required),
            "allowed_actions": ["approve", "reject", "request_revision"]
            if human_review_required
            else [],
        },
        "safety": {
            "automatic_publish": False,
            "report_generated_from_existing_run": True,
            "no_live_fetch": True,
            "no_real_llm_call": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    event = report.get("event", {})
    sources = report.get("sources", {})
    risk = report.get("risk_and_fact", {})
    run = report.get("agent_run", {})
    trace = report.get("trace", {})
    review = report.get("human_review", {})
    safety = report.get("safety", {})

    lines = [
        "# CrisisAgent 危机处理报告",
        "",
        "## 1. 事件概览",
        f"- 事件 ID：{event.get('event_id', '')}",
        f"- 标题：{event.get('title', '')}",
        f"- 公司：{event.get('company', '')}",
        f"- 事件状态：{event.get('status', '')}",
        f"- 创建时间：{event.get('created_at', '')}",
        f"- 更新时间：{event.get('updated_at', '')}",
        "",
        "## 2. 舆情来源",
        f"- source_run_id：{sources.get('source_run_id', '')}",
        f"- cluster_id：{sources.get('cluster_id', '')}",
        f"- source_count：{sources.get('source_count', 0)}",
        f"- source_items：{_display_list(sources.get('source_items'))}",
        f"- 首次发布时间：{sources.get('first_published_at', '')}",
        f"- 最近发布时间：{sources.get('last_published_at', '')}",
        f"- event_fingerprint：{sources.get('event_fingerprint', '')}",
        "",
        "## 3. 风险与事实状态",
        f"- risk_level：{risk.get('risk_level', '')}",
        f"- public_emotion：{risk.get('public_emotion', '')}",
        f"- fact_status：{risk.get('fact_status', '')}",
        f"- event_status：{risk.get('event_status', '')}",
        f"- human_review_required：{risk.get('human_review_required', False)}",
        "",
        "## 4. Agent 处理流程",
        f"- agent_run_id：{run.get('agent_run_id', '')}",
        f"- session_id：{run.get('session_id', '')}",
        f"- run_status：{run.get('run_status', '')}",
        f"- mode：{run.get('mode', '')}",
        f"- agent 顺序：{_display_list(trace.get('agent_order'))}",
        f"- scores：{_inline_json(run.get('scores', {}))}",
        "",
        "## 5. Legal RAG 证据摘要",
        _inline_json(trace.get("legal_rag_evidence", {})),
        "",
        "## 6. RedTeam 审查摘要",
        _display_list(trace.get("redteam_issues")) or "not_available",
        "",
        "## 7. 最终声明草稿",
        "以下内容是 Agent 生成的声明草稿，不代表已经发布：",
        "",
        str(run.get("final_statement_preview", "")) or "not_available",
        "",
        "## 8. Human Review 状态",
        f"- human_review_required：{review.get('human_review_required', False)}",
        f"- policy_triggers：{_display_list(review.get('policy_triggers'))}",
        f"- review_reason：{review.get('review_reason', '')}",
        f"- approval_status：{review.get('approval_status')}",
        f"- allowed_actions：{_display_list(review.get('allowed_actions'))}",
        "",
        "## 9. 安全边界",
        f"- automatic_publish：{safety.get('automatic_publish', False)}",
        f"- report_generated_from_existing_run：{safety.get('report_generated_from_existing_run', True)}",
        f"- no_live_fetch：{safety.get('no_live_fetch', True)}",
        f"- no_real_llm_call：{safety.get('no_real_llm_call', True)}",
        "",
        "## 10. 后续建议",
        "在人工确认事实、来源和风险后，再通过现有审核流程决定是否继续处理；本报告本身不会自动发布声明。",
        "",
    ]
    return "\n".join(lines)


def _build_trace_summary(trace: list[dict[str, Any]]) -> dict[str, Any]:
    agents = []
    summaries = []
    redteam_issues: list[Any] = []
    legal_rag: dict[str, Any] | None = None
    decision_statement = ""

    for item in trace:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", ""))
        if agent:
            agents.append(agent)
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        summaries.append(
            {
                "agent": agent,
                "status": item.get("status", ""),
                "output_summary": _preview(output or item.get("output")),
            }
        )
        if agent == "redteam":
            redteam_issues.extend(_as_list(output.get("issues")))
        if agent == "legal":
            candidate = item.get("rag")
            if isinstance(candidate, dict):
                evidence = candidate.get("evidence_chunks") or candidate.get("chunks")
                legal_rag = candidate if evidence else {
                    "status": "not_available",
                    "evidence_chunks": [],
                }
        if agent == "decision":
            decision_statement = str(output.get("final_statement") or output.get("statement") or "")

    return {
        "agent_order": agents,
        "agent_summaries": summaries,
        "redteam_issues": redteam_issues,
        "legal_rag_evidence": legal_rag or {"status": "not_available", "evidence_chunks": []},
        "decision_final_statement": decision_statement,
    }


def _approval_status(run: dict[str, Any], required: bool) -> str | None:
    approval = run.get("approval")
    if isinstance(approval, dict) and approval.get("decision"):
        return str(approval["decision"])
    return "pending" if required else None


def _review_reason(triggers: list[str], required: bool) -> str:
    if not required:
        return ""
    return "Human review required: " + ", ".join(triggers)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _preview(value: Any, max_length: int = 240) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    text = str(value or "")
    return text if len(text) <= max_length else text[:max_length] + "..."


def _display_list(value: Any) -> str:
    values = _as_list(value)
    return ", ".join(str(item) for item in values) if values else "empty"


def _inline_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
