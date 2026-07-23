import re
from pathlib import Path

from backend.rag.document_loader import KNOWLEDGE_BASE_DIR, load_documents
from backend.rag.text_splitter import split_documents


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")


def retrieve(query: str, top_k: int = 3, knowledge_base_dir: str | Path = KNOWLEDGE_BASE_DIR) -> dict:
    documents = load_documents(knowledge_base_dir)
    chunks = split_documents(documents)
    query_tokens = _tokenize(query)

    scored_chunks = []
    for chunk in chunks:
        score = _score_chunk(query_tokens, chunk["text"])
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    top_chunks = scored_chunks[:top_k]

    return {
        "context": _format_context(top_chunks),
        "sources": [
            {
                "source": chunk["source"],
                "title": chunk["title"],
                "score": round(score, 4),
            }
            for score, chunk in top_chunks
        ],
    }


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for match in _TOKEN_PATTERN.findall(text.lower()):
        tokens.add(match)
        if _contains_chinese(match):
            for index in range(len(match) - 1):
                tokens.add(match[index : index + 2])
    return tokens


def _score_chunk(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0

    chunk_tokens = _tokenize(text)
    if not chunk_tokens:
        return 0.0

    overlap = query_tokens & chunk_tokens
    return len(overlap) / len(query_tokens)


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _format_context(scored_chunks: list[tuple[float, dict]]) -> str:
    context_parts = []
    for score, chunk in scored_chunks:
        context_parts.append(
            f"[{chunk['source']} | score={round(score, 4)}]\n{chunk['text']}"
        )
    return "\n\n".join(context_parts)
