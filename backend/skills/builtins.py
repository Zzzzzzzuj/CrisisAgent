from __future__ import annotations

from typing import Any

from backend.core.checkpoint import load_checkpoint
from backend.guardrails.input_guardrail import evaluate_input_guardrail
from backend.guardrails.output_guardrail import evaluate_output_guardrail
from backend.observability.metrics import collect_runtime_metrics
from backend.rag.knowledge_repository import KnowledgeRepository
from backend.rag.retriever import retrieve
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill


def create_default_registry() -> SkillRegistry:
    return SkillRegistry(
        [
            _legal_rag_search_skill(),
            _session_lookup_skill(),
            _runtime_metrics_query_skill(),
            _guardrail_check_skill(),
            _knowledge_document_search_skill(),
        ]
    )


def _legal_rag_search_skill() -> AgentSkill:
    return AgentSkill(
        name="legal_rag_search",
        description="Search Legal RAG evidence for a crisis-response query.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "sources": {"type": "array"},
                "chunks": {"type": "array"},
                "fallback_used": {"type": "boolean"},
            },
        },
        category="rag",
        owner_agent="legal_agent",
        safety_level="medium",
        enabled=True,
        version="1.0",
        handler=_execute_legal_rag_search,
    )


def _session_lookup_skill() -> AgentSkill:
    return AgentSkill(
        name="session_lookup",
        description="Load a CrisisAgent session checkpoint by session_id.",
        input_schema={
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "found": {"type": "boolean"},
                "session": {"type": "object"},
            },
        },
        category="runtime",
        owner_agent="runtime",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=_execute_session_lookup,
    )


def _runtime_metrics_query_skill() -> AgentSkill:
    return AgentSkill(
        name="runtime_metrics_query",
        description="Return lightweight runtime metrics from the current checkpoint backend.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        category="observability",
        owner_agent="runtime",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=lambda payload: collect_runtime_metrics(),
    )


def _guardrail_check_skill() -> AgentSkill:
    return AgentSkill(
        name="guardrail_check",
        description="Evaluate input and/or output guardrails without calling an LLM.",
        input_schema={
            "type": "object",
            "properties": {
                "event": {"type": "string"},
                "statement": {"type": "string"},
            },
            "required": [],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "input": {"type": "object"},
                "output": {"type": "object"},
                "hit": {"type": "boolean"},
            },
        },
        category="safety",
        owner_agent="guardrails",
        safety_level="high",
        enabled=True,
        version="1.0",
        handler=_execute_guardrail_check,
    )


def _knowledge_document_search_skill() -> AgentSkill:
    return AgentSkill(
        name="knowledge_document_search",
        description="List managed knowledge documents by optional source_category.",
        input_schema={
            "type": "object",
            "properties": {
                "source_category": {"type": "string"},
                "published_only": {"type": "boolean"},
            },
            "required": [],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "documents": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        category="knowledge",
        owner_agent="legal_agent",
        safety_level="low",
        enabled=True,
        version="1.0",
        handler=_execute_knowledge_document_search,
    )


def _execute_legal_rag_search(payload: dict[str, Any]) -> dict[str, Any]:
    result = retrieve(payload["query"], top_k=int(payload.get("top_k", 3)))
    return {
        "context": result.get("context", ""),
        "sources": result.get("sources", []),
        "chunks": result.get("chunks", []),
        "fallback_used": bool(result.get("fallback_used", False)),
    }


def _execute_session_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    state = load_checkpoint(payload["session_id"])
    return {
        "found": state is not None,
        "session": state.to_dict() if state is not None else {},
    }


def _execute_guardrail_check(payload: dict[str, Any]) -> dict[str, Any]:
    input_result = evaluate_input_guardrail(payload.get("event", ""))
    output_result = evaluate_output_guardrail(payload.get("statement", ""))
    return {
        "input": input_result,
        "output": output_result,
        "hit": bool(input_result.get("hit") or output_result.get("hit")),
    }


def _execute_knowledge_document_search(payload: dict[str, Any]) -> dict[str, Any]:
    repository = KnowledgeRepository()
    documents = (
        repository.load_published_documents()
        if payload.get("published_only", False)
        else repository.list_documents()
    )
    category = payload.get("source_category")
    if category:
        documents = [item for item in documents if item.get("source_category") == category]
    return {
        "documents": documents,
        "count": len(documents),
    }
