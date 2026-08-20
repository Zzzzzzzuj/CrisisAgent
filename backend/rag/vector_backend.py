import os


DEFAULT_VECTOR_BACKEND = "json"
DEFAULT_PGVECTOR_INDEX_TYPE = "ivfflat"
DEFAULT_PGVECTOR_DISTANCE = "cosine"


def get_vector_backend() -> str:
    backend = os.getenv("VECTOR_BACKEND", DEFAULT_VECTOR_BACKEND).strip().lower()
    if backend == "pgvector":
        return "pgvector"
    return "json"


def get_pgvector_index_type() -> str:
    index_type = os.getenv("PGVECTOR_INDEX_TYPE", DEFAULT_PGVECTOR_INDEX_TYPE).strip().lower()
    if index_type in {"ivfflat", "hnsw", "none"}:
        return index_type
    return DEFAULT_PGVECTOR_INDEX_TYPE


def get_pgvector_distance() -> str:
    distance = os.getenv("PGVECTOR_DISTANCE", DEFAULT_PGVECTOR_DISTANCE).strip().lower()
    if distance in {"cosine", "l2"}:
        return distance
    return DEFAULT_PGVECTOR_DISTANCE


def is_pgvector_backend_enabled() -> bool:
    return get_vector_backend() == "pgvector"
