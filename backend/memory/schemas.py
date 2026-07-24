from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    event_summary: str
    category: str
    risk_level: str
    public_emotion: str
    successful_strategy: str
    legal_lessons: list[str]
    public_opinion_lessons: list[str]
    final_statement_preview: str
    scores: dict
    tags: list[str]
    created_at: str

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "event_summary": self.event_summary,
            "category": self.category,
            "risk_level": self.risk_level,
            "public_emotion": self.public_emotion,
            "successful_strategy": self.successful_strategy,
            "legal_lessons": self.legal_lessons,
            "public_opinion_lessons": self.public_opinion_lessons,
            "final_statement_preview": self.final_statement_preview,
            "scores": self.scores,
            "tags": self.tags,
            "created_at": self.created_at,
        }


def create_memory_item(
    event_summary: str,
    category: str,
    risk_level: str,
    public_emotion: str,
    successful_strategy: str,
    legal_lessons: list[str],
    public_opinion_lessons: list[str],
    final_statement_preview: str,
    scores: dict,
    tags: list[str],
    memory_id: str | None = None,
    created_at: str | None = None,
) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id or str(uuid4()),
        event_summary=event_summary,
        category=category,
        risk_level=risk_level,
        public_emotion=public_emotion,
        successful_strategy=successful_strategy,
        legal_lessons=legal_lessons,
        public_opinion_lessons=public_opinion_lessons,
        final_statement_preview=final_statement_preview,
        scores=scores,
        tags=tags,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )
