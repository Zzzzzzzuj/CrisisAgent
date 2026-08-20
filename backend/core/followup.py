from __future__ import annotations

from typing import Any

from backend.core.state import AgentState


FOLLOWUP_TYPES = {
    "clarification",
    "rewrite",
    "media_qna",
    "internal_action",
    "regulator_response",
}


def build_followup_response(state: AgentState, question: str, followup_type: str) -> dict[str, Any]:
    normalized_type = str(followup_type or "clarification").strip().lower()
    if normalized_type not in FOLLOWUP_TYPES:
        raise ValueError(f"Unsupported followup_type: {followup_type}")
    question_text = str(question or "").strip()
    if not question_text:
        raise ValueError("Field 'question' is required.")

    context = _session_context(state)
    response = _mock_followup_answer(question_text, normalized_type, context)
    return {
        "session_id": state.session_id,
        "followup_type": normalized_type,
        "question": question_text,
        "answer": response,
        "mode": "mock",
        "used_session_state": True,
        "context_summary": {
            "event": state.event,
            "final_statement_present": bool(context["final_statement"]),
            "trace_items": len(state.trace or []),
            "rag_evidence_count": len(context["rag_evidence"]),
            "scores": context["scores"],
        },
    }


def _session_context(state: AgentState) -> dict[str, Any]:
    results = state.get_all_results()
    decision = results.get("decision", {})
    writer_v2 = results.get("writer_v2", {})
    final_statement = decision.get("final_statement") or writer_v2.get("statement") or ""
    return {
        "event": state.event,
        "final_statement": final_statement,
        "scores": decision.get("scores", {}),
        "rag_evidence": _rag_evidence_from_trace(state.trace),
        "guardrails": state.metadata.get("guardrails", {}),
        "approval": state.approval,
    }


def _rag_evidence_from_trace(trace: list) -> list[dict]:
    evidence = []
    for item in trace or []:
        rag = item.get("rag") if isinstance(item, dict) else None
        if not isinstance(rag, dict):
            continue
        chunks = rag.get("evidence_chunks") or rag.get("chunks") or []
        for chunk in chunks:
            if isinstance(chunk, dict):
                evidence.append(
                    {
                        "source": chunk.get("source") or chunk.get("source_name"),
                        "source_category": chunk.get("source_category"),
                        "text_preview": chunk.get("text_preview") or str(chunk.get("text", ""))[:120],
                    }
                )
    return evidence


def _mock_followup_answer(question: str, followup_type: str, context: dict[str, Any]) -> str:
    final_statement = context["final_statement"] or "当前 session 尚未形成最终声明。"
    evidence_count = len(context["rag_evidence"])
    if followup_type == "rewrite":
        return f"基于原事件和现有最终声明，建议改写时保留审慎口径：{final_statement}"
    if followup_type == "media_qna":
        return f"媒体问答建议：先回应事实核查进展，再说明用户保护措施。本回答参考了 {evidence_count} 条 RAG evidence。"
    if followup_type == "internal_action":
        return "内部行动建议：同步法务、公关、客服和业务负责人，复核 trace 中的风险点、证据来源和人工审核意见。"
    if followup_type == "regulator_response":
        return "监管回应建议：说明已启动核查、保留证据、按要求配合检查，并避免在事实未明前作绝对定性。"
    return f"澄清答复：该问题会结合原始事件、最终声明、评分和 {evidence_count} 条 RAG evidence 处理。问题是：{question}"
