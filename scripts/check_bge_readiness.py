import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MODEL_NAME = "BAAI/bge-small-zh"
DEFAULT_TEXTS = [
    "食品品牌被曝使用过期原料",
    "APP发生用户个人信息泄露",
    "网站服务大面积宕机",
]


def check_bge_readiness(
    model_name: str = DEFAULT_MODEL_NAME,
    texts: list[str] | None = None,
    model_cls=None,
) -> dict[str, Any]:
    sample_texts = texts or DEFAULT_TEXTS
    started_at = time.perf_counter()

    try:
        if model_cls is None:
            from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

            model_cls = BGEEmbeddingModel

        model = model_cls(model_name=model_name)
        cold_load_ms = _elapsed_ms(started_at)

        vectors = []
        single_times = []
        for text in sample_texts:
            embed_started_at = time.perf_counter()
            vector = model.embed(text)
            single_times.append(_elapsed_ms(embed_started_at))
            vectors.append(vector)

        batch_started_at = time.perf_counter()
        batch_vectors = model._model.encode(sample_texts, normalize_embeddings=True)
        warm_batch_embedding_ms = _elapsed_ms(batch_started_at)

        return {
            "status": "BGE_READY",
            "model_name": model_name,
            "embedding_dimension": len(vectors[0]) if vectors else 0,
            "shape": _shape(batch_vectors, vectors),
            "dtype": str(getattr(batch_vectors, "dtype", type(vectors[0][0]).__name__ if vectors and vectors[0] else None)),
            "norms": [_norm(vector) for vector in vectors],
            "has_nan": [any(math.isnan(value) for value in vector) for vector in vectors],
            "has_inf": [any(math.isinf(value) for value in vector) for vector in vectors],
            "cold_model_load_ms": round(cold_load_ms, 2),
            "warm_batch_embedding_ms": round(warm_batch_embedding_ms, 2),
            "per_text_average_embedding_ms": round(sum(single_times) / len(single_times), 2)
            if single_times
            else 0.0,
        }
    except Exception as exc:
        return {
            "status": "BGE_NOT_AVAILABLE",
            "model_name": model_name,
            "reason": classify_bge_failure(exc),
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "elapsed_ms": round(_elapsed_ms(started_at), 2),
            "setup_hint": (
                "Install optional dependencies with `pip install -r requirements-bge.txt`, "
                "then cache the model with "
                "`python -c \"from sentence_transformers import SentenceTransformer; "
                "SentenceTransformer('BAAI/bge-small-zh')\"`."
            ),
        }


def classify_bge_failure(exc: Exception) -> str:
    message = str(exc).lower()
    exception_name = type(exc).__name__.lower()

    if "sentence-transformers" in message or "sentence_transformers" in message:
        return "dependency_missing"
    if "cache" in message and ("couldn't connect" in message or "offline" in message):
        return "model_not_cached"
    if "cannot find the requested files" in message:
        return "model_not_cached"
    if "permission" in message or "拒绝访问" in message:
        return "cache_permission_error"
    if "couldn't connect" in message or "connection" in message or "network" in message:
        return "network_unavailable"
    if "import" in exception_name:
        return "dependency_missing"
    return "initialization_error"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether BGE embedding is ready for real use.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    args = parser.parse_args()

    result = check_bge_readiness(model_name=args.model_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "BGE_READY" else 1


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _norm(vector: list[float]) -> float:
    return round(math.sqrt(sum(value * value for value in vector)), 6)


def _shape(batch_vectors, vectors: list[list[float]]) -> list[int]:
    shape = getattr(batch_vectors, "shape", None)
    if shape is not None:
        return [int(value) for value in shape]
    return [len(vectors), len(vectors[0]) if vectors else 0]


if __name__ == "__main__":
    raise SystemExit(main())
