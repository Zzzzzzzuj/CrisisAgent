import os
from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert input text into a numeric vector."""


def get_embedding_model(model_name: str | None = None) -> EmbeddingModel:
    selected_model = (model_name or os.getenv("EMBEDDING_MODEL", "hash")).strip().lower()

    if selected_model == "hash":
        return HashEmbeddingModel()
    if selected_model == "bge":
        return BGEEmbeddingModel()

    raise ValueError("EMBEDDING_MODEL must be either 'hash' or 'bge'.")


from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel
from backend.rag.embeddings.hash_embedding import HashEmbeddingModel


__all__ = [
    "BGEEmbeddingModel",
    "EmbeddingModel",
    "HashEmbeddingModel",
    "get_embedding_model",
]
