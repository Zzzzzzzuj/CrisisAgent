from dataclasses import dataclass


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
