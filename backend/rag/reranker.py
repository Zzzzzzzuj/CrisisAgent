import re

from backend.rag.schemas import RetrievalResult, RetrievedChunk


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
_SOURCE_HINTS = {
    "food": "food_safety.md",
    "食品": "food_safety.md",
    "原料": "food_safety.md",
    "监管": "food_safety.md",
    "legal": "legal_risk_rules.md",
    "法律": "legal_risk_rules.md",
    "定责": "legal_risk_rules.md",
    "责任": "legal_risk_rules.md",
    "危机": "crisis_response.md",
    "回应": "crisis_response.md",
    "舆情": "crisis_response.md",
}


class RuleBasedReranker:
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 3,
    ) -> RetrievalResult:
        if top_k <= 0 or not chunks:
            return RetrievalResult(context="", chunks=[], sources=[])

        reranked_chunks = [_rerank_chunk(query, chunk) for chunk in chunks]
        reranked_chunks.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
        top_chunks = reranked_chunks[:top_k]

        return RetrievalResult(
            context=_format_context(top_chunks),
            chunks=top_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "rerank_score": chunk.rerank_score,
                }
                for chunk in top_chunks
            ],
        )


def rerank(query: str, chunks: list[RetrievedChunk], top_k: int = 3) -> RetrievalResult:
    return RuleBasedReranker().rerank(query, chunks, top_k)


def _rerank_chunk(query: str, chunk: RetrievedChunk) -> RetrievedChunk:
    title_score = _title_match_score(query, chunk.title)
    source_score = _source_match_score(query, chunk.source)
    overlap_score = _keyword_overlap_score(query, chunk.text)
    rerank_score = (
        0.5 * chunk.score
        + 0.2 * title_score
        + 0.15 * source_score
        + 0.15 * overlap_score
    )
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "title_match_score": round(title_score, 4),
            "source_match_score": round(source_score, 4),
            "keyword_overlap_score": round(overlap_score, 4),
        }
    )

    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=round(rerank_score, 4),
    )


def _title_match_score(query: str, title: str) -> float:
    return _keyword_overlap_score(query, title)


def _source_match_score(query: str, source: str) -> float:
    for keyword, expected_source in _SOURCE_HINTS.items():
        if keyword in query and expected_source == source:
            return 1.0
    return 0.0


def _keyword_overlap_score(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)

    if not query_tokens or not text_tokens:
        return 0.0

    return len(query_tokens & text_tokens) / len(query_tokens)


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for match in _TOKEN_PATTERN.findall(text.lower()):
        tokens.add(match)
        if _contains_chinese(match):
            for index in range(len(match) - 1):
                tokens.add(match[index : index + 2])
    return tokens


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[{chunk.source} | score={chunk.score} | rerank_score={chunk.rerank_score}]\n{chunk.text}"
        )
    return "\n\n".join(context_parts)
