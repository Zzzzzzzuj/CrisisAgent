import os
from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert input text into a numeric vector."""


def get_embedding_model(model_name: str | None = None) -> EmbeddingModel:
    selected_model = (model_name or os.getenv("EMBEDDING_MODEL", "hash")).strip().lower()

    if selected_model == "hash":
        HashEmbeddingModel = globals().get("HashEmbeddingModel")
        if HashEmbeddingModel is None:
            from backend.rag.embeddings.hash_embedding import HashEmbeddingModel

        return HashEmbeddingModel()
    if selected_model == "bge":
        BGEEmbeddingModel = globals().get("BGEEmbeddingModel")
        if BGEEmbeddingModel is None:
            from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

        return BGEEmbeddingModel()

    raise ValueError("EMBEDDING_MODEL must be either 'hash' or 'bge'.")


def __getattr__(name: str):
    if name == "HashEmbeddingModel":
        from backend.rag.embeddings.hash_embedding import HashEmbeddingModel

        return HashEmbeddingModel
    if name == "BGEEmbeddingModel":
        from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

        return BGEEmbeddingModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BGEEmbeddingModel",
    "EmbeddingModel",
    "HashEmbeddingModel",
    "get_embedding_model",
]
