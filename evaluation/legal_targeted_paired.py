"""Frozen, offline broad-vs-targeted evaluation using the real local RAG pipeline."""

import hashlib
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch

from backend.agents.legal_agent import _build_retrieval_query
from backend.agents.legal_action_policy import TARGETED_LEGAL_SEARCH, recommend_legal_actions
from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_relation import build_legal_claim_relations
from backend.agents.legal_targeted_search import _targeted_query
from backend.rag.document_loader import KNOWLEDGE_BASE_DIR, load_chunks
from backend.rag.embeddings.hash_embedding import HashEmbeddingModel
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.query_rewriter import rewrite_query
from backend.rag.reranker import RuleBasedReranker
from backend.rag.vector_retriever import VectorRetriever


DEFAULT_CASES = Path(__file__).resolve().parents[1] / "data" / "legal_targeted_paired_cases.json"
PRODUCTION_TOP_K = 3
MIN_RERANK_SCORE = 0.1


def _ref(chunk) -> str:
    metadata = chunk.metadata if hasattr(chunk, "metadata") else chunk.get("metadata", {})
    source = chunk.source if hasattr(chunk, "source") else chunk["source"]
    if not isinstance(metadata, dict) or type(metadata.get("section_index")) is not int:
        raise ValueError("Local chunk is missing a stable section reference.")
    return f"{source}#section-{metadata['section_index']}:chunk-{metadata['chunk_index']}"


def _normalized_kb_hash(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _RecordingHybrid:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def retrieve(self, query, top_k=3):
        result = self.delegate.retrieve(query, top_k=top_k)
        self.calls.append({"query": query, "refs": [_ref(chunk) for chunk in result.chunks]})
        return result


class _RecordingReranker:
    def __init__(self):
        self.delegate = RuleBasedReranker()
        self.candidate_refs = []
        self.full_ranking = []

    def rerank(self, query, chunks, top_k=3):
        self.candidate_refs = sorted({_ref(chunk) for chunk in chunks})
        result = self.delegate.rerank(query, chunks, top_k=top_k)
        diagnostic = self.delegate.rerank(query, chunks, top_k=len(chunks))
        self.full_ranking = [
            {"rank": index, "evidence_ref": _ref(chunk), "score": chunk.score,
             "rerank_score": chunk.rerank_score}
            for index, chunk in enumerate(diagnostic.chunks, 1)
        ]
        return result


def _validate_frozen_set(data: dict, kb_dir: Path) -> set[str]:
    hashes = data.get("kb_sha256")
    if not isinstance(hashes, dict) or set(hashes) != {p.name for p in kb_dir.glob("*.md")}:
        raise ValueError("Frozen KB file inventory does not match the local KB.")
    for filename, expected_hash in hashes.items():
        actual_hash = _normalized_kb_hash(kb_dir / filename)
        if actual_hash != expected_hash:
            raise ValueError(f"Frozen KB changed: {filename}")
    available_refs = {_ref(chunk) for chunk in load_chunks(kb_dir)}
    seen_ids = set()
    for case in data.get("cases", []):
        case_id = case.get("case_id")
        label = case.get("label")
        expected = case.get("expected_evidence_refs")
        if not isinstance(case_id, str) or case_id in seen_ids or label not in {"positive", "negative"}:
            raise ValueError("Invalid or duplicate frozen case.")
        seen_ids.add(case_id)
        if not isinstance(expected, list) or (label == "positive" and not expected) or (label == "negative" and expected):
            raise ValueError(f"Invalid expected refs: {case_id}")
        if len(set(expected)) != len(expected) or not set(expected) <= available_refs:
            raise ValueError(f"Expected evidence is absent from frozen KB: {case_id}")
        if label == "positive" and case.get("material_kind") not in {
            "rule_like", "response_constraint", "response_guidance",
        }:
            raise ValueError(f"Missing candidate material type: {case_id}")
        if not all(isinstance(case.get(key), str) and case[key].strip() for key in
                   ("claim", "event_context", "draft_context")):
            raise ValueError(f"Incomplete frozen case: {case_id}")
        if not isinstance(case.get("redteam_context"), dict):
            raise ValueError(f"Missing RedTeam context: {case_id}")
    if not seen_ids:
        raise ValueError("Frozen evaluation set is empty.")
    return available_refs


def _side(query: str, pipeline, hybrid_recorder, rerank_recorder, claim: str) -> dict:
    hybrid_recorder.calls = []
    rerank_recorder.candidate_refs = []
    rerank_recorder.full_ranking = []
    rewritten = rewrite_query(query)
    start = perf_counter()
    result = pipeline.retrieve(query, top_k=PRODUCTION_TOP_K)
    latency_ms = round((perf_counter() - start) * 1000, 3)
    calls = list(hybrid_recorder.calls)
    chunks = result.chunks
    rows = []
    for rank, chunk in enumerate(chunks, 1):
        ref = _ref(chunk)
        first_query = next((item["query"] for item in calls if ref in item["refs"]), None)
        metadata = chunk.metadata or {}
        rows.append({
            "rank": rank, "evidence_ref": ref, "chunk_id": chunk.chunk_id,
            "document_id": metadata.get("document_id"),
            "document_version": metadata.get("document_version"),
            "source": chunk.source, "score": chunk.score,
            "rerank_score": chunk.rerank_score,
            "matched_query": metadata.get("matched_query"),
            "first_recall_query": first_query,
        })
    claim_record = {"claim": claim, "requires_legal_rule": True, "requires_case_fact": False}
    relation = build_legal_claim_relations([claim_record], [chunk.to_dict() for chunk in chunks], mode="mock")
    coverage = build_claim_coverage([claim_record], relation)
    fallback_used = any((chunk.metadata or {}).get("retrieval_fallback") is True for chunk in chunks)
    recommendation = recommend_legal_actions(
        {"legal_claims": [claim_record]}, coverage, relation,
        {"retrieval_status": "executed_with_hits" if chunks else "executed_no_hit",
         "retrieval_executed": True, "fallback_used": fallback_used},
    )["claim_action_recommendations"][0]
    return {
        "original_query": query, "rewritten_queries": rewritten,
        "rewritten_query_count": len(rewritten),
        "pipeline_query_calls": [item["query"] for item in calls],
        "top_k": PRODUCTION_TOP_K, "latency_ms": latency_ms,
        "candidate_refs_before_rerank": list(rerank_recorder.candidate_refs),
        "full_rerank_diagnostic": list(rerank_recorder.full_ranking),
        "results": rows, "relation": relation,
        "legal_rule_status": coverage["claim_coverage"][0]["legal_rule_status"],
        "p32_recommendation": recommendation,
        "fallback_used": fallback_used,
    }


def _rank(side: dict, expected: set[str]) -> int | None:
    return next((row["rank"] for row in side["results"] if row["evidence_ref"] in expected), None)


def _first_recall_kind(targeted: dict, broad: dict, expected: set[str]) -> str | None:
    hit = next((row for row in targeted["results"] if row["evidence_ref"] in expected), None)
    if hit is None:
        return None
    first = hit["first_recall_query"]
    if first is None:
        return "unavailable"
    if first == targeted["original_query"]:
        return "original_targeted_query"
    return "shared_rewrite" if first in broad["rewritten_queries"] else "targeted_only_rewrite"


def _outcome(broad_rank: int | None, targeted_rank: int | None) -> str:
    if broad_rank and targeted_rank:
        return "BOTH"
    if targeted_rank:
        return "TARGETED_ONLY"
    if broad_rank:
        return "BROAD_ONLY"
    return "NEITHER"


def run_legal_targeted_paired_eval(cases_path: str | Path = DEFAULT_CASES) -> dict:
    """No database, network, LLM, Redis, or BGE is used by this evaluation."""
    data = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    kb_dir = KNOWLEDGE_BASE_DIR
    # The production retriever classes are unchanged; only their data source and backend are pinned.
    with patch.dict(os.environ, {"CHECKPOINT_STORAGE": "json", "VECTOR_BACKEND": "json",
                               "EMBEDDING_MODEL": "hash"}), patch(
        "backend.rag.document_loader._load_database_chunks_if_available", return_value=[]
    ):
        _validate_frozen_set(data, kb_dir)
        keyword = KeywordRetriever(kb_dir)
        vector = VectorRetriever(embedding_model=HashEmbeddingModel(), knowledge_base_dir=kb_dir,
                                 vector_backend="json")
        hybrid_recorder = _RecordingHybrid(HybridRetriever(keyword, vector))
        rerank_recorder = _RecordingReranker()
        pipeline = RagPipelineRetriever(hybrid_retriever=hybrid_recorder, reranker=rerank_recorder,
                                        fallback_retriever=keyword, min_rerank_score=MIN_RERANK_SCORE)
        rows = []
        for case in data["cases"]:
            broad_query = _build_retrieval_query({
                "event": case["event_context"], "draft": case["draft_context"],
                "redteam_review": case["redteam_context"],
            })
            targeted_query = _targeted_query(case["claim"], broad_query)
            if not targeted_query:
                raise ValueError(f"P33 did not produce a distinct targeted query: {case['case_id']}")
            broad = _side(broad_query, pipeline, hybrid_recorder, rerank_recorder, case["claim"])
            targeted = _side(targeted_query, pipeline, hybrid_recorder, rerank_recorder, case["claim"])
            if (broad["pipeline_query_calls"] != broad["rewritten_queries"] or
                    targeted["pipeline_query_calls"] != targeted["rewritten_queries"]):
                raise ValueError("The local pipeline fell back or did not execute every rewritten query.")
            expected = set(case["expected_evidence_refs"])
            broad_rank, targeted_rank = _rank(broad, expected), _rank(targeted, expected)
            shared = sorted(set(broad["rewritten_queries"]) & set(targeted["rewritten_queries"]))
            row = {
                "case_id": case["case_id"], "label": case["label"],
                "material_kind": case.get("material_kind"),
                "claim": case["claim"], "expected_evidence_refs": sorted(expected),
                "broad": broad, "targeted": targeted,
                "rewrite_overlap": {"shared": shared, "shared_count": len(shared),
                                    "broad_only": [q for q in broad["rewritten_queries"] if q not in shared],
                                    "targeted_only": [q for q in targeted["rewritten_queries"] if q not in shared]},
            }
            if case["label"] == "positive":
                outcome = _outcome(broad_rank, targeted_rank)
                broad_candidates = set(broad["candidate_refs_before_rerank"])
                targeted_candidates = set(targeted["candidate_refs_before_rerank"])
                row.update({
                    "paired_outcome": outcome, "broad_rank": broad_rank,
                    "targeted_rank": targeted_rank,
                    "p33_eligible_from_broad": broad["p32_recommendation"]["recommended_action"]
                    == TARGETED_LEGAL_SEARCH,
                    "rank_delta_broad_minus_targeted": broad_rank - targeted_rank
                    if broad_rank is not None and targeted_rank is not None else None,
                    "candidate_set_equal": broad_candidates == targeted_candidates,
                    "target_in_broad_candidates": bool(expected & broad_candidates),
                    "target_in_targeted_candidates": bool(expected & targeted_candidates),
                    "targeted_first_recall_kind": _first_recall_kind(targeted, broad, expected),
                    "broad_target_full_rerank": next((item for item in broad["full_rerank_diagnostic"]
                                                      if item["evidence_ref"] in expected), None),
                    "targeted_target_full_rerank": next((item for item in targeted["full_rerank_diagnostic"]
                                                         if item["evidence_ref"] in expected), None),
                })
                if outcome == "NEITHER":
                    row["failure_class"] = "retrieval_or_ranking_miss_in_existing_kb"
                elif outcome == "BROAD_ONLY":
                    row["failure_class"] = "targeted_query_lost_expected_material"
            else:
                row["negative_observation"] = {
                    "broad_candidate_rule_relations": sum(
                        item["relation"] == "candidate_rule_relevant" for item in broad["relation"]["legal_claim_relations"]),
                    "targeted_candidate_rule_relations": sum(
                        item["relation"] == "candidate_rule_relevant" for item in targeted["relation"]["legal_claim_relations"]),
                    "broad_top_rerank_score": broad["results"][0]["rerank_score"] if broad["results"] else None,
                    "targeted_top_rerank_score": targeted["results"][0]["rerank_score"] if targeted["results"] else None,
                    "broad_top_source": broad["results"][0]["source"] if broad["results"] else None,
                    "targeted_top_source": targeted["results"][0]["source"] if targeted["results"] else None,
                }
            rows.append(row)

    positives = [row for row in rows if row["label"] == "positive"]
    negatives = [row for row in rows if row["label"] == "negative"]
    eligible_positives = [row for row in positives if row["p33_eligible_from_broad"]]
    counts = {name: sum(row["paired_outcome"] == name for row in positives)
              for name in ("BOTH", "TARGETED_ONLY", "BROAD_ONLY", "NEITHER")}
    eligible_counts = {name: sum(row["paired_outcome"] == name for row in eligible_positives)
                       for name in counts}
    relation_after_hit = {}
    for side_name in ("broad", "targeted"):
        hits = [row for row in positives if row[f"{side_name}_rank"] is not None]
        relation_after_hit[side_name] = {
            status: sum(row[side_name]["legal_rule_status"] == status for row in hits)
            for status in ("candidate_found", "uncertain", "no_candidate")
        }
    by_material_kind = {}
    for kind in sorted({row["material_kind"] for row in positives}):
        subset = [row for row in positives if row["material_kind"] == kind]
        by_material_kind[kind] = {
            "cases": len(subset),
            "broad_hit_at_3": sum(row["broad_rank"] is not None for row in subset),
            "targeted_hit_at_3": sum(row["targeted_rank"] is not None for row in subset),
            "p33_eligible_targeted_only": sum(
                row["p33_eligible_from_broad"] and row["paired_outcome"] == "TARGETED_ONLY"
                for row in subset
            ),
        }
    return {
        "dataset_version": data["dataset_version"], "kb_sha256": data["kb_sha256"],
        "configuration": {"kb": "frozen_local_markdown", "embedding": "hash-128",
                          "vector_backend": "json", "pipeline": "RagPipelineRetriever",
                          "top_k": PRODUCTION_TOP_K, "min_rerank_score": MIN_RERANK_SCORE,
                          "reranker": "RuleBasedReranker"},
        "positive_cases": len(positives), "negative_cases": len(negatives),
        "paired_outcome_counts": counts,
        "p33_eligible_positive_cases": len(eligible_positives),
        "p33_eligible_paired_outcome_counts": eligible_counts,
        "hit_at_1": {side: sum(row[f"{side}_rank"] == 1 for row in positives)
                     for side in ("broad", "targeted")},
        "hit_at_3": {side: sum(row[f"{side}_rank"] is not None for row in positives)
                     for side in ("broad", "targeted")},
        "target_retrieved_relation_coverage": relation_after_hit,
        "by_material_kind": by_material_kind,
        "latency_ms_median": {side: round(median(row[side]["latency_ms"] for row in rows), 3)
                              for side in ("broad", "targeted")},
        "additional_retrieval_call_per_eligible_case": 1,
        "cases": rows,
        "limitations": [
            "Local hash embedding is not BGE; no live traffic or LLM is evaluated.",
            "KB contains response guidance as well as rule-like material; target Hit@K is not legal accuracy.",
            "matched_query is the retained highest-scoring query variant, not necessarily first recall.",
            "All-case paired outcomes include cases where P32 would not permit P33 execution.",
            "Latency is descriptive for this local process only; no token cost is inferred.",
        ],
    }
