import json
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.factory import get_retriever

DEFAULT_CASES_PATH = PROJECT_ROOT / "data" / "rag_retrieval_eval_cases.json"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "reports" / "rag_retrieval_eval_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "reports" / "rag_retrieval_eval_report.md"


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_cases(
    cases: list[dict],
    top_k: int = 3,
    retriever: Any | None = None,
) -> dict:
    os.environ.setdefault("VECTOR_BACKEND", "json")
    active_retriever = retriever or get_retriever("pipeline")
    evaluated_cases = [
        _evaluate_case(case, active_retriever, top_k=top_k)
        for case in cases
    ]
    summary = _summarize(evaluated_cases)
    return {
        "summary": summary,
        "cases": evaluated_cases,
        "empty_knowledge_base_hint": _empty_knowledge_base_hint(evaluated_cases),
    }


def write_reports(
    result: dict,
    json_path: str | Path = DEFAULT_REPORT_JSON,
    markdown_path: str | Path = DEFAULT_REPORT_MD,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_target.write_text(_render_markdown(result), encoding="utf-8")


def main() -> int:
    cases = load_cases()
    result = evaluate_cases(cases)
    write_reports(result)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if result["empty_knowledge_base_hint"]:
        print(result["empty_knowledge_base_hint"])
    print(f"JSON report: {DEFAULT_REPORT_JSON}")
    print(f"Markdown report: {DEFAULT_REPORT_MD}")
    return 0


def _evaluate_case(case: dict, retriever: Any, top_k: int) -> dict:
    retrieval = retriever.retrieve(case["crisis_event"], top_k=top_k)
    retrieval_dict = retrieval.to_dict() if hasattr(retrieval, "to_dict") else dict(retrieval)
    chunks = retrieval_dict.get("chunks", [])
    top_chunks = [_chunk_summary(chunk) for chunk in chunks[:top_k]]
    actual_categories = [
        chunk.get("source_category")
        for chunk in top_chunks
        if chunk.get("source_category")
    ]
    expected_category = case["expected_source_category"]
    top1_source_hit = bool(actual_categories[:1] and actual_categories[0] == expected_category)
    top3_source_hit = expected_category in actual_categories[:3]
    keyword_hits = _keyword_hits(case.get("expected_keywords", []), chunks)
    fallback_used = any(chunk.get("fallback_used") for chunk in top_chunks)
    scores = [chunk["score"] for chunk in top_chunks if isinstance(chunk.get("score"), (int, float))]
    rerank_scores = [
        chunk["rerank_score"]
        for chunk in top_chunks
        if isinstance(chunk.get("rerank_score"), (int, float))
    ]
    return {
        "case_id": case["case_id"],
        "difficulty": case["difficulty"],
        "crisis_event": case["crisis_event"],
        "expected_source_category": expected_category,
        "expected_document_hint": case["expected_document_hint"],
        "expected_keywords": case.get("expected_keywords", []),
        "actual_source_categories": actual_categories,
        "top1_source_hit": top1_source_hit,
        "top3_source_hit": top3_source_hit,
        "keyword_hits": keyword_hits,
        "keyword_hit": len(keyword_hits) == len(case.get("expected_keywords", [])),
        "fallback_used": fallback_used,
        "average_score": round(mean(scores), 4) if scores else 0.0,
        "average_rerank_score": round(mean(rerank_scores), 4) if rerank_scores else 0.0,
        "top_chunks": top_chunks,
        "failure_reason": _failure_reason(expected_category, actual_categories, keyword_hits, case),
        "notes": case.get("notes", ""),
    }


def _chunk_summary(chunk: dict) -> dict:
    metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
    text = str(chunk.get("text", ""))
    retrieval_backend = metadata.get("retrieval_backend")
    if not retrieval_backend:
        retrieval_backend = "markdown" if str(chunk.get("source", "")).endswith(".md") else "unknown"
    return {
        "chunk_id": chunk.get("chunk_id"),
        "source": chunk.get("source"),
        "title": chunk.get("title"),
        "source_category": metadata.get("source_category"),
        "document_id": metadata.get("document_id"),
        "document_version": metadata.get("document_version"),
        "document_status": metadata.get("document_status"),
        "is_enabled": metadata.get("is_enabled"),
        "source_name": metadata.get("source_name"),
        "score": chunk.get("score"),
        "rerank_score": chunk.get("rerank_score"),
        "fallback_used": metadata.get("retrieval_fallback", False),
        "retrieval_backend": retrieval_backend,
        "text_preview": text[:180],
    }


def _keyword_hits(expected_keywords: list[str], chunks: list[dict]) -> list[str]:
    evidence_text = "\n".join(
        str(chunk.get("text", "")) + "\n" + str(chunk.get("metadata", {}).get("text_preview", ""))
        for chunk in chunks
        if isinstance(chunk, dict)
    )
    return [keyword for keyword in expected_keywords if keyword in evidence_text]


def _summarize(cases: list[dict]) -> dict:
    total = len(cases)
    scores = [
        chunk["score"]
        for case in cases
        for chunk in case["top_chunks"]
        if isinstance(chunk.get("score"), (int, float))
    ]
    rerank_scores = [
        chunk["rerank_score"]
        for case in cases
        for chunk in case["top_chunks"]
        if isinstance(chunk.get("rerank_score"), (int, float))
    ]
    return {
        "total_cases": total,
        "top1_source_hit_rate": _rate(case["top1_source_hit"] for case in cases),
        "top3_source_hit_rate": _rate(case["top3_source_hit"] for case in cases),
        "keyword_hit_rate": _rate(case["keyword_hit"] for case in cases),
        "fallback_rate": _rate(case["fallback_used"] for case in cases),
        "average_score": round(mean(scores), 4) if scores else 0.0,
        "average_rerank_score": round(mean(rerank_scores), 4) if rerank_scores else 0.0,
        "backend_distribution": _backend_distribution(cases),
        "failed_cases": [
            case["case_id"]
            for case in cases
            if not case["top3_source_hit"] or not case["keyword_hit"]
        ],
    }


def _rate(flags) -> float:
    values = list(flags)
    if not values:
        return 0.0
    return round(sum(1 for value in values if value) / len(values), 4)


def _backend_distribution(cases: list[dict]) -> dict:
    distribution: dict[str, int] = {}
    for case in cases:
        for chunk in case["top_chunks"]:
            backend = chunk.get("retrieval_backend") or "unknown"
            distribution[backend] = distribution.get(backend, 0) + 1
    return distribution


def _failure_reason(
    expected_category: str,
    actual_categories: list[str],
    keyword_hits: list[str],
    case: dict,
) -> str:
    if not actual_categories:
        return "no_retrieval_result"
    if expected_category not in actual_categories[:3]:
        return "expected_source_category_not_in_top3"
    missing_keywords = set(case.get("expected_keywords", [])) - set(keyword_hits)
    if missing_keywords:
        return "expected_keywords_missing"
    return ""


def _empty_knowledge_base_hint(cases: list[dict]) -> str:
    if cases and all(not case["top_chunks"] for case in cases):
        return (
            "No RAG chunks were returned. If you expected database-backed retrieval, "
            "run: python scripts/ingest_knowledge_base.py --path backend/rag/knowledge_base"
        )
    return ""


def _render_markdown(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# RAG Retrieval Evaluation Report",
        "",
        "This is a lightweight offline Legal RAG retrieval benchmark. It does not call a real LLM.",
        "",
        "## Summary",
        "",
        f"- total_cases: {summary['total_cases']}",
        f"- top1_source_hit_rate: {summary['top1_source_hit_rate']}",
        f"- top3_source_hit_rate: {summary['top3_source_hit_rate']}",
        f"- keyword_hit_rate: {summary['keyword_hit_rate']}",
        f"- fallback_rate: {summary['fallback_rate']}",
        f"- average_score: {summary['average_score']}",
        f"- average_rerank_score: {summary['average_rerank_score']}",
        f"- backend_distribution: {summary['backend_distribution']}",
        "",
        "## Cases",
        "",
    ]
    for case in result["cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- difficulty: {case['difficulty']}",
                f"- expected_source_category: {case['expected_source_category']}",
                f"- actual_source_categories: {case['actual_source_categories']}",
                f"- top1_source_hit: {case['top1_source_hit']}",
                f"- top3_source_hit: {case['top3_source_hit']}",
                f"- keyword_hits: {case['keyword_hits']}",
                f"- fallback_used: {case['fallback_used']}",
                f"- failure_reason: {case['failure_reason'] or 'none'}",
                "",
                "| rank | source | category | score | rerank_score | backend | preview |",
                "|---:|---|---|---:|---:|---|---|",
            ]
        )
        for index, chunk in enumerate(case["top_chunks"], start=1):
            preview = str(chunk.get("text_preview", "")).replace("|", " ").replace("\n", " ")
            lines.append(
                f"| {index} | {chunk.get('source')} | {chunk.get('source_category')} | "
                f"{chunk.get('score')} | {chunk.get('rerank_score')} | "
                f"{chunk.get('retrieval_backend')} | {preview} |"
            )
        lines.append("")
    if result.get("empty_knowledge_base_hint"):
        lines.extend(["## Empty Knowledge Base Hint", "", result["empty_knowledge_base_hint"], ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
