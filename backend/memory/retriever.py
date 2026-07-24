import re
from pathlib import Path

from backend.memory.storage import MEMORY_FILE, list_memories


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")


def retrieve_memories(
    query: str,
    top_k: int = 3,
    memory_file: str | Path = MEMORY_FILE,
) -> dict:
    if top_k <= 0:
        return {"memories": [], "context": ""}

    query_tokens = _tokenize(query)
    scored_memories = []
    for memory in list_memories(memory_file):
        score = _score_memory(query_tokens, memory)
        if score > 0:
            scored_memories.append((score, memory))

    scored_memories.sort(key=lambda item: item[0], reverse=True)
    top_memories = [
        {
            **memory,
            "score": round(score, 4),
        }
        for score, memory in scored_memories[:top_k]
    ]

    return {
        "memories": top_memories,
        "context": _format_context(top_memories),
    }


def _score_memory(query_tokens: set[str], memory: dict) -> float:
    if not query_tokens:
        return 0.0

    memory_text = " ".join(
        [
            str(memory.get("event_summary", "")),
            str(memory.get("category", "")),
            str(memory.get("risk_level", "")),
            str(memory.get("public_emotion", "")),
            str(memory.get("successful_strategy", "")),
            " ".join(memory.get("legal_lessons", [])),
            " ".join(memory.get("public_opinion_lessons", [])),
            " ".join(memory.get("tags", [])),
        ]
    )
    memory_tokens = _tokenize(memory_text)
    if not memory_tokens:
        return 0.0

    return len(query_tokens & memory_tokens) / len(query_tokens)


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


def _format_context(memories: list[dict]) -> str:
    context_parts = []
    for memory in memories:
        context_parts.append(
            "\n".join(
                [
                    f"[memory_id={memory['memory_id']} | score={memory['score']}]",
                    f"event_summary: {memory.get('event_summary', '')}",
                    f"category: {memory.get('category', '')}",
                    f"successful_strategy: {memory.get('successful_strategy', '')}",
                    f"legal_lessons: {memory.get('legal_lessons', [])}",
                    f"public_opinion_lessons: {memory.get('public_opinion_lessons', [])}",
                ]
            )
        )
    return "\n\n".join(context_parts)
