import hashlib
import math
import re

from backend.rag.embedding import EmbeddingModel


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class HashEmbeddingModel(EmbeddingModel):
    def __init__(self, dimension: int = 128):
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _tokenize(text)

        if not tokens:
            return vector

        for token in tokens:
            index = _stable_hash(token) % self.dimension
            vector[index] += 1.0

        return _normalize(vector)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _stable_hash(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest, 16)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
