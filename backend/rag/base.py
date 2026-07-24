from abc import ABC, abstractmethod

from backend.rag.schemas import RetrievalResult


class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        """Return the most relevant knowledge chunks for a query."""
