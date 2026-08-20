import os
from contextvars import ContextVar
from copy import deepcopy

from backend.config import get_config
from backend.llm import LLMClient
from backend.llm.client import get_last_llm_trace, record_llm_fallback
from backend.llm.parser import parse_json_response, validate_required_fields
from backend.logger import get_logger
from backend.rag.retrieval_need_gate import evaluate_retrieval_need
from backend.rag.retriever import retrieve


logger = get_logger(__name__)
AGENT_NAME = "Agent B"
_DEFAULT_RAG_INFO = {
    "enabled": False,
    "hit": False,
    "rag_used": False,
    "retrieval_backend": "none",
    "retrieval_type": None,
    "rerank_enabled": False,
    "query": "",
    "retrieval_query": "",
    "sources": [],
    "source_details": [],
    "chunks": [],
    "evidence_chunks": [],
    "evidence_summary": "RAG was not used.",
    "scores": [],
    "rerank_scores": [],
    "count": 0,
    "fallback_used": False,
    "gate": {},
    "retrieval_skipped": False,
    "retrieval_executed": False,
    "retrieval_status": "not_started",
}
_LAST_RAG_INFO = deepcopy(_DEFAULT_RAG_INFO)
_RAG_INFO_CONTEXT: ContextVar[dict] = ContextVar("legal_rag_info_context", default=deepcopy(_DEFAULT_RAG_INFO))
REQUIRED_FIELDS = (
    "legal_risks",
    "safe_points",
    "revision_advice",
    "public_opinion_suggestions",
    "integrated_revision_tasks",
)


def run(payload: dict) -> dict:
    config = get_config()

    if config.agent_mode == "llm":
        _set_rag_info(enabled=True, hit=False, sources=[])
        try:
            return _attach_metadata(_run_llm(payload))
        except Exception as exc:
            logger.warning(
                "%s fallback to mock mode due to llm failure: %s | %s",
                AGENT_NAME,
                exc.__class__.__name__,
                str(exc),
            )
            llm_trace = record_llm_fallback(AGENT_NAME, exc)
            return _attach_metadata(_run_mock(payload), llm_trace=llm_trace)

    _set_rag_info(enabled=False, hit=False, sources=[])
    return _attach_metadata(_run_mock(payload))


def get_last_rag_info() -> dict:
    return deepcopy(_RAG_INFO_CONTEXT.get(_LAST_RAG_INFO))


def _set_rag_info(
    enabled: bool,
    hit: bool,
    sources: list[str],
    source_details: list[dict] | None = None,
    query: str = "",
    chunks: list[dict] | None = None,
    retrieval_type: str | None = None,
    rerank_enabled: bool = False,
    fallback_used: bool = False,
    gate: dict | None = None,
    retrieval_skipped: bool = False,
    retrieval_executed: bool = False,
    retrieval_status: str = "not_started",
) -> None:
    chunks = chunks or []
    gate = gate or {}
    source_details = source_details or []
    evidence_chunks = _build_evidence_chunks(chunks, source_details)
    retrieval_backend = _resolve_retrieval_backend(evidence_chunks, source_details, retrieval_status)
    rag_used = enabled and retrieval_executed and bool(evidence_chunks)
    evidence_summary = _build_evidence_summary(
        rag_used=rag_used,
        retrieval_status=retrieval_status,
        retrieval_backend=retrieval_backend,
        evidence_chunks=evidence_chunks,
        gate=gate,
    )
    # sources/count describe unique source files; scores describe final retrieved chunks.
    rag_info = {
            "enabled": enabled,
            "hit": hit,
            "rag_used": rag_used,
            "retrieval_backend": retrieval_backend,
            "retrieval_type": retrieval_type,
            "rerank_enabled": rerank_enabled,
            "query": query,
            "retrieval_query": query,
            "sources": sources,
            "source_details": source_details,
            "chunks": chunks,
            "evidence_chunks": evidence_chunks,
            "evidence_summary": evidence_summary,
            "scores": [chunk.get("score") for chunk in chunks],
            "rerank_scores": [chunk.get("rerank_score") for chunk in chunks],
            "count": len(sources),
            "fallback_used": fallback_used,
            "gate": dict(gate),
            "retrieval_skipped": retrieval_skipped,
            "retrieval_executed": retrieval_executed,
            "retrieval_status": retrieval_status,
    }
    _LAST_RAG_INFO.clear()
    _LAST_RAG_INFO.update(deepcopy(rag_info))
    _RAG_INFO_CONTEXT.set(deepcopy(rag_info))


def _run_mock(payload: dict) -> dict:
    draft = payload["draft"]
    redteam_review = payload["redteam_review"]
    redteam_suggestions = redteam_review.get("suggestions", [])
    legal_risks = []

    if "确认" in draft or "确实" in draft:
        legal_risks.append("存在在调查完成前直接确认事实的风险。")
    if "一定" in draft or "绝不" in draft:
        legal_risks.append("存在绝对化承诺风险。")
    if "负责到底" in draft:
        legal_risks.append("责任表达过满，可能引发额外法律解释空间。")

    public_opinion_suggestions = []
    for suggestion in redteam_suggestions:
        if "公众" in suggestion or "消费者" in suggestion or "担忧" in suggestion:
            public_opinion_suggestions.append(suggestion)
        elif "核查" in suggestion or "处理承诺" in suggestion:
            public_opinion_suggestions.append(suggestion)

    if not public_opinion_suggestions and redteam_suggestions:
        public_opinion_suggestions = redteam_suggestions[:2]

    integrated_revision_tasks = [
        "保留对公众担忧和消费者不安的明确回应，避免只做程序性表态。",
        "补充核查范围、后续整改和处理动作，但不要提前认定全部事实。",
        "涉及责任时使用条件式表达，例如以核查结果为前提依法依规处理。",
        "避免绝对化承诺，同时让回应看起来不是模板化推责。",
    ]

    return _normalize_output(
        {
            "legal_risks": legal_risks or ["未发现明显高风险承认性表述，但仍需保持条件式措辞。"],
            "safe_points": [
                "使用了核查、配合监管等相对稳妥表达。",
                "未直接下结论认定全部事实成立。",
            ],
            "revision_advice": [
                "保留对事件的重视与歉意，但避免提前定责。",
                "如需提及责任，建议加上核查结果前提。",
                "避免使用绝对化保证性语言。",
            ],
            "public_opinion_suggestions": public_opinion_suggestions,
            "integrated_revision_tasks": integrated_revision_tasks,
            "legal_safety_score_hint": 8,
            "review_summary": "当前草稿整体偏稳妥。结合红队反馈后，建议同时增强公众沟通力度，并继续坚持调查中、配合监管、依法处理的表达方式。",
        }
    )


def _run_llm(payload: dict) -> dict:
    legal_context = _retrieve_legal_context(payload)
    prompt = _build_legal_prompt(payload, legal_context)
    raw_text = call_llm(prompt)
    parsed = parse_json_response(raw_text)
    validate_required_fields(parsed, REQUIRED_FIELDS)

    validated = _validate_output(parsed)
    logger.info("%s parsed llm result: %s", AGENT_NAME, validated)

    mapped_output = {
        "legal_risks": validated["legal_risks"],
        "safe_points": validated["safe_points"],
        "revision_advice": validated["revision_advice"],
        "public_opinion_suggestions": validated["public_opinion_suggestions"],
        "integrated_revision_tasks": validated["integrated_revision_tasks"],
        "legal_safety_score_hint": validated.get("legal_safety_score_hint", 8),
        "review_summary": validated.get(
            "review_summary",
            "当前草稿整体偏稳妥，建议继续坚持调查中、配合监管、依法处理的表达方式。",
        ),
    }
    normalized_output = _normalize_output(mapped_output)
    logger.info("%s normalized output: %s", AGENT_NAME, normalized_output)
    return normalized_output


def call_llm(prompt: str) -> str:
    client = LLMClient()
    if client.config.mock_enabled:
        raise RuntimeError("LLM_API_KEY is not configured; fallback to mock legal agent.")
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": "You are CrisisAgent Legal Agent B. Return JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
        agent_name=AGENT_NAME,
    )


def _build_legal_prompt(payload: dict, legal_context: str) -> str:
    return f"""
你是 CrisisAgent 的合规审查 Agent B，角色是企业危机公关合规审核专家。

输入事件 event：
{payload["event"]}

待审核声明 draft：
{payload["draft"]}

红队反馈 redteam_review：
{payload["redteam_review"]}

检索到的合规知识 retrieved_context：
{legal_context}
legal_context: {legal_context}

审查要求：
- 优先参考 retrieved_context / legal_context 中的法律风险规范、企业危机回应规范和历史案例经验。
- 不要编造不存在的法律条文；如果知识不足，请在建议中保持审慎表达。
- 检查是否提前确认事实、提前定责、使用绝对化承诺或过度承诺。
- 检查是否包含调查/核查、整改、监管配合、后续更新等安全表达。
- 结合 redteam_review，把公众质疑建议整理进 public_opinion_suggestions。
- integrated_revision_tasks 必须是给 Writer Agent 第二版修改使用的任务清单。

只输出 JSON，不要输出 markdown，不要输出额外解释。JSON schema：
{{
  "legal_risks": [],
  "safe_points": [],
  "revision_advice": [],
  "public_opinion_suggestions": [],
  "integrated_revision_tasks": [],
  "legal_safety_score_hint": 8,
  "review_summary": ""
}}
""".strip()


def _retrieve_legal_context(payload: dict) -> str:
    query = _build_retrieval_query(payload)
    if not _is_rag_enabled():
        _set_rag_info(
            enabled=False,
            hit=False,
            sources=[],
            query=query,
            retrieval_skipped=True,
            retrieval_executed=False,
            retrieval_status="disabled",
        )
        logger.info("%s RAG disabled by RAG_ENABLED=false", AGENT_NAME)
        return ""

    gate = evaluate_retrieval_need(
        event=payload.get("event", ""),
        draft=payload.get("draft", ""),
        redteam_review=payload.get("redteam_review", {}),
    )

    if not gate.get("need_rag", False):
        _set_rag_info(
            enabled=True,
            hit=False,
            sources=[],
            query=query,
            gate=gate,
            retrieval_skipped=True,
            retrieval_executed=False,
            retrieval_status="skipped_by_gate",
        )
        logger.info("%s RAG skipped by retrieval need gate: %s", AGENT_NAME, gate)
        return ""

    try:
        retrieval_result = retrieve(query, top_k=3)
    except Exception as exc:
        logger.warning(
            "%s RAG retrieval failed: %s | %s",
            AGENT_NAME,
            exc.__class__.__name__,
            str(exc),
        )
        _set_rag_info(
            enabled=True,
            hit=False,
            sources=[],
            query=query,
            gate=gate,
            retrieval_skipped=False,
            retrieval_executed=True,
            fallback_used=True,
            retrieval_status="retrieval_error",
        )
        return ""

    sources = retrieval_result.get("sources", [])
    chunks = _normalize_rag_chunks(retrieval_result.get("chunks", []), query)
    source_names = []
    source_details = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("source"):
            continue
        source_name = str(source["source"])
        if source_name not in source_names:
            source_names.append(source_name)
            source_details.append(
                {
                    "source": source_name,
                    "title": source.get("title"),
                    "document_id": source.get("document_id"),
                    "document_version": source.get("document_version"),
                    "chunk_id": source.get("chunk_id"),
                    "source_category": source.get("source_category"),
                    "document_status": source.get("document_status"),
                    "is_enabled": source.get("is_enabled"),
                    "source_name": source.get("source_name") or source.get("source") or source.get("title"),
                    "score": source.get("score"),
                    "rerank_score": source.get("rerank_score"),
                    "retrieval_query": query,
                    "fallback_used": source.get("retrieval_fallback", False),
                    "retrieval_backend": source.get("retrieval_backend"),
                    "vector_backend": source.get("vector_backend"),
                    "pgvector_fallback_used": source.get("pgvector_fallback_used", False),
                }
            )
    _set_rag_info(
        enabled=True,
        hit=bool(source_names),
        sources=source_names,
        source_details=source_details,
        query=query,
        chunks=chunks,
        retrieval_type=_resolve_retrieval_type(retrieval_result),
        rerank_enabled=_resolve_rerank_enabled(retrieval_result),
        fallback_used=_resolve_retrieval_fallback(retrieval_result),
        gate=gate,
        retrieval_skipped=False,
        retrieval_executed=True,
        retrieval_status="executed_with_hits" if source_names else "executed_no_hit",
    )
    logger.info("%s RAG retrieved %s sources: %s", AGENT_NAME, len(sources), sources)
    return retrieval_result.get("context", "")


def _normalize_rag_chunks(chunks: list[dict], retrieval_query: str = "") -> list[dict]:
    normalized_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        normalized_chunks.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": metadata.get("document_id"),
                "document_version": metadata.get("document_version"),
                "source": chunk.get("source"),
                "source_category": metadata.get("source_category"),
                "document_status": metadata.get("document_status"),
                "is_enabled": metadata.get("is_enabled"),
                "source_name": metadata.get("source_name") or chunk.get("source") or chunk.get("title"),
                "title": chunk.get("title"),
                "score": chunk.get("score"),
                "rerank_score": chunk.get("rerank_score"),
                "retrieval_query": retrieval_query,
                "fallback_used": metadata.get("retrieval_fallback", False),
                "retrieval_backend": metadata.get("retrieval_backend"),
                "vector_backend": metadata.get("vector_backend"),
                "pgvector_fallback_used": metadata.get("pgvector_fallback_used", False),
                "text_preview": str(chunk.get("text", ""))[:120],
            }
        )
    return normalized_chunks


def _attach_metadata(output: dict, llm_trace: dict | None = None) -> dict:
    enriched = dict(output)
    metadata = {
        "rag": get_last_rag_info(),
    }
    llm = llm_trace if llm_trace is not None else get_last_llm_trace()
    if llm:
        metadata["llm"] = deepcopy(llm)
    enriched["_metadata"] = metadata
    return enriched


def _is_rag_enabled() -> bool:
    return os.getenv("RAG_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _build_evidence_chunks(chunks: list[dict], source_details: list[dict]) -> list[dict]:
    evidence = []
    if chunks:
        for chunk in chunks:
            evidence.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "document_version": chunk.get("document_version"),
                    "source": chunk.get("source"),
                    "source_category": chunk.get("source_category"),
                    "document_status": chunk.get("document_status"),
                    "is_enabled": chunk.get("is_enabled"),
                    "source_name": chunk.get("source_name"),
                    "score": chunk.get("score"),
                    "rerank_score": chunk.get("rerank_score"),
                    "retrieval_backend": chunk.get("retrieval_backend"),
                    "vector_backend": chunk.get("vector_backend"),
                    "pgvector_fallback_used": chunk.get("pgvector_fallback_used", False),
                    "text_preview": str(chunk.get("text_preview", ""))[:200],
                }
            )
        return evidence

    for source in source_details:
        evidence.append(
            {
                "chunk_id": source.get("chunk_id"),
                "document_id": source.get("document_id"),
                "document_version": source.get("document_version"),
                "source": source.get("source"),
                "source_category": source.get("source_category"),
                "document_status": source.get("document_status"),
                "is_enabled": source.get("is_enabled"),
                "source_name": source.get("source_name"),
                "score": source.get("score"),
                "rerank_score": source.get("rerank_score"),
                "retrieval_backend": source.get("retrieval_backend"),
                "vector_backend": source.get("vector_backend"),
                "pgvector_fallback_used": source.get("pgvector_fallback_used", False),
                "text_preview": "",
            }
        )
    return evidence


def _resolve_retrieval_backend(
    evidence_chunks: list[dict],
    source_details: list[dict],
    retrieval_status: str,
) -> str:
    if retrieval_status in {"disabled", "skipped_by_gate", "not_started"}:
        return "none"
    metadata_rows = evidence_chunks or source_details
    for row in metadata_rows:
        backend = row.get("retrieval_backend")
        if backend:
            return str(backend)
    if any(row.get("document_id") or row.get("document_version") for row in metadata_rows):
        return "db"
    if metadata_rows:
        return "markdown"
    return "none"


def _build_evidence_summary(
    rag_used: bool,
    retrieval_status: str,
    retrieval_backend: str,
    evidence_chunks: list[dict],
    gate: dict,
) -> str:
    if retrieval_status == "disabled":
        return "RAG was disabled by RAG_ENABLED=false; Legal Agent reviewed without retrieved evidence."
    if retrieval_status == "skipped_by_gate":
        reason = gate.get("reason", "retrieval need gate rejected RAG")
        return f"RAG was skipped by gate: {reason}"
    if retrieval_status == "retrieval_error":
        return "RAG retrieval failed; Legal Agent continued with empty context and fallback metadata."
    if not rag_used:
        return "RAG executed but returned no relevant evidence chunks."
    sources = []
    for chunk in evidence_chunks:
        source = chunk.get("source")
        if source and source not in sources:
            sources.append(source)
    return (
        f"Legal Agent used {len(evidence_chunks)} evidence chunks "
        f"from {retrieval_backend} backend: {', '.join(sources)}."
    )


def _resolve_retrieval_type(retrieval_result: dict) -> str | None:
    for chunk in retrieval_result.get("chunks", []):
        metadata = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
        if metadata.get("retrieval_type"):
            return metadata["retrieval_type"]
    for source in retrieval_result.get("sources", []):
        if isinstance(source, dict) and source.get("retrieval_type"):
            return source["retrieval_type"]
    return None


def _resolve_rerank_enabled(retrieval_result: dict) -> bool:
    for chunk in retrieval_result.get("chunks", []):
        metadata = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
        if metadata.get("rerank_enabled"):
            return True
    return any(
        isinstance(source, dict) and source.get("rerank_enabled")
        for source in retrieval_result.get("sources", [])
    )


def _resolve_retrieval_fallback(retrieval_result: dict) -> bool:
    for chunk in retrieval_result.get("chunks", []):
        metadata = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
        if metadata.get("retrieval_fallback"):
            return True
    return any(
        isinstance(source, dict) and source.get("retrieval_fallback")
        for source in retrieval_result.get("sources", [])
    )


def _build_retrieval_query(payload: dict) -> str:
    redteam_review = payload["redteam_review"]
    return "\n".join(
        [
            f"事件：{payload['event']}",
            f"声明草稿：{payload['draft']}",
            f"红队问题：{redteam_review.get('issues', [])}",
            f"红队建议：{redteam_review.get('suggestions', [])}",
        ]
    )


def _validate_output(payload: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    for field in REQUIRED_FIELDS:
        if not isinstance(payload[field], list):
            raise TypeError(f"Field '{field}' must be a list.")
        if not all(isinstance(item, str) for item in payload[field]):
            raise TypeError(f"All items in '{field}' must be strings.")

    if "legal_safety_score_hint" in payload and not isinstance(payload["legal_safety_score_hint"], int):
        raise TypeError("Field 'legal_safety_score_hint' must be an integer when provided.")
    if "review_summary" in payload and not isinstance(payload["review_summary"], str):
        raise TypeError("Field 'review_summary' must be a string when provided.")

    return payload


def _normalize_output(payload: dict) -> dict:
    return {
        "legal_risks": [str(item) for item in payload["legal_risks"]],
        "safe_points": [str(item) for item in payload["safe_points"]],
        "revision_advice": [str(item) for item in payload["revision_advice"]],
        "public_opinion_suggestions": [str(item) for item in payload["public_opinion_suggestions"]],
        "integrated_revision_tasks": [str(item) for item in payload["integrated_revision_tasks"]],
        "legal_safety_score_hint": int(payload.get("legal_safety_score_hint", 8)),
        "review_summary": str(
            payload.get(
                "review_summary",
                "当前草稿整体偏稳妥，建议继续坚持调查中、配合监管、依法处理的表达方式。",
            )
        ),
    }
