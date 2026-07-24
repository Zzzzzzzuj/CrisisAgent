from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    source: str
    title: str
    content: str

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "content": self.content,
        }


@dataclass(frozen=True)
class KnowledgeChunk:
    text: str
    source: str
    title: str

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "title": self.title,
        }


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    title: str
    score: float
    chunk_id: str | None = None
    metadata: dict[str, Any] | None = None
    embedding_score: float | None = None
    rerank_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "title": self.title,
            "score": self.score,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata or {},
            "embedding_score": self.embedding_score,
            "rerank_score": self.rerank_score,
        }


@dataclass(frozen=True)
class RetrievalResult:
    context: str
    chunks: list[RetrievedChunk]
    sources: list[dict]

    def to_dict(self) -> dict:
        return {
            "context": self.context,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "sources": self.sources,
        }
