import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.reranker import RuleBasedReranker
from backend.rag.retrieval_need_gate import evaluate_retrieval_need
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.rag.vector_retriever import VectorRetriever
from evaluation.rag_gate_challenge_v3_evaluator import normalize_case_for_retrieval
from evaluation.rag_metrics_v2 import evaluate_retrieval_case, summarize_subset


CHALLENGE_PATH = PROJECT_ROOT / "evaluation" / "rag_gate_challenge_v3.json"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "latest_reranker_v2_development.md"
TOP_K = 5
MIN_RERANK_SCORE = 0.1
BGE_MODEL_NAME = "BAAI/bge-small-zh"

SOURCE_CATEGORY = {
    "food_safety.md": "food_safety",
    "data_privacy.md": "data_privacy",
    "service_outage.md": "service_outage",
    "product_quality.md": "product_quality",
    "executive_misconduct.md": "executive_misconduct",
    "crisis_response.md": "crisis_response",
    "legal_risk_rules.md": "legal",
}
BASELINE_FORMULA = (
    "0.5 * retrieval_score + 0.2 * title_match "
    "+ 0.15 * source_match + 0.15 * keyword_overlap"
)
V2_FORMULA = (
    "0.48 * retrieval_score + 0.17 * title_match "
    "+ 0.10 * source_match + 0.14 * keyword_overlap + domain_adjustment"
)
DEVELOPMENT_SELECTION_RULE = {
    "recall_at_3_min": 0.90,
    "context_pollution_below": "same_scope_baseline",
    "source_category_match_above": "same_scope_baseline",
    "no_large_retrieval_miss": True,
}
EVALUATION_SCOPE = {
    "name": "Phase 4B Reranker Development",
    "evaluation_scope": "positive_only",
    "dataset_scope": "Challenge v3 positive cases only",
    "total_cases": 20,
    "gate_applied": True,
    "gate_version": "Gate v3",
    "dedupe_level": "source",
    "retrieval_unit": "deduped source document",
    "case_set_status": "post-hoc development only",
    "direct_comparison_allowed": "baseline_vs_reranker_v2_same_scope_only",
}
CANONICAL_CHALLENGE_V3_METRICS = {
    "scope": "40 cases: 20 positive + 20 negative",
    "gate_applied": True,
    "dedupe_level": "source",
    "purpose": "Gate + Retriever overall evaluation",
    "directly_comparable_to_phase4b": False,
    "recall_at_1": 0.65,
    "recall_at_3": 0.95,
    "recall_at_5": 0.95,
    "precision_at_1": 0.325,
    "precision_at_3": 0.1583,
    "precision_at_5": 0.095,
    "mrr": 0.7917,
    "no_hit_accuracy": 0.85,
    "source_category_match": 0.4933,
    "context_pollution_rate": 0.3733,
}
PHASE4A_POLLUTION_AUDIT_SCOPE = {
    "scope": "Challenge v3 positive cases, chunk-level trace",
    "gate_applied": False,
    "dedupe_level": "none",
    "retrieval_unit": "chunk",
    "purpose": "Locate where pollution first appears across retrieval stages.",
    "directly_comparable_to_phase4b_wrong_rank": False,
}
METRIC_DEFINITIONS = {
    "precision_at_k": {
        "per_case": (
            "len(set(deduped_retrieved_sources[:k]) & acceptable_sources) / k"
        ),
        "aggregation": "average over the 20 positive development cases",
        "note": (
            "Challenge v3 canonical Precision@K averages over 40 cases, so its "
            "P@1=0.325 is not directly comparable to Phase 4B positive-only "
            "baseline P@1=0.65."
        ),
    },
    "source_category_match": {
        "per_case": (
            "matched acceptable deduped sources / retrieved deduped sources; "
            "empty retrieval returns 1.0"
        ),
        "aggregation": "weighted average with weight=max(1, source_count)",
    },
    "context_pollution_rate": {
        "per_case": (
            "forbidden deduped sources or forbidden categories / retrieved "
            "deduped sources; empty retrieval returns 0.0"
        ),
        "aggregation": "weighted average with weight=max(1, source_count)",
        "valid_comparison": (
            "Phase 4B baseline 0.4314 -> reranker_v2 0.1765 is same-scope "
            "and directly comparable; Challenge v3 canonical 0.3733 must not "
            "be used as the Phase 4B before value."
        ),
    },
    "gate_rejected_positive": {
        "case_id": "gate_challenge_v3_data_privacy_004",
        "behavior": "Gate v3 returns need_rag=false, so retrieval is empty.",
        "metric_effect": (
            "Recall@K=0, Precision@K=0, reciprocal_rank=0, "
            "source_category_match=1.0, context_pollution_rate=0.0, "
            "source_count weight=1."
        ),
    },
    "wrong_rank": {
        "phase4a": "chunk-level, non-deduped, no Gate",
        "phase4b": "source-level, deduped, Gate-applied",
        "note": (
            "Phase 4A rank distribution must not be compared directly with "
            "Phase 4B wrong-rank distribution. Phase 4B baseline and v2 can "
            "be compared because they share one evaluator."
        ),
    },
}


class BaselineRuleBasedReranker:
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = TOP_K,
    ) -> RetrievalResult:
        if top_k <= 0 or not chunks:
            return RetrievalResult(context="", chunks=[], sources=[])

        reranked_chunks = [_baseline_rerank_chunk(query, chunk) for chunk in chunks]
        reranked_chunks.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
        top_chunks = reranked_chunks[:top_k]
        return RetrievalResult(
            context=_format_context(top_chunks),
            chunks=top_chunks,
            sources=[_source_dict(chunk) for chunk in top_chunks],
        )


def run_development_evaluation() -> dict:
    cases = load_positive_challenge_cases()
    baseline = evaluate_variant("baseline", BaselineRuleBasedReranker(), cases)
    reranker_v2 = evaluate_variant("reranker_v2", RuleBasedReranker(), cases)
    comparison = compare_variants(baseline, reranker_v2)
    return {
        "experiment": "Domain-Aware RuleBasedReranker Development",
        "dataset": str(CHALLENGE_PATH.relative_to(PROJECT_ROOT)),
        "scope": "post-hoc development only",
        "challenge_v3_status": "no longer untouched",
        "metric_scope": EVALUATION_SCOPE,
        "canonical_challenge_v3_metrics": CANONICAL_CHALLENGE_V3_METRICS,
        "phase4a_pollution_audit_scope": PHASE4A_POLLUTION_AUDIT_SCOPE,
        "metric_definitions": METRIC_DEFINITIONS,
        "python_executable": sys.executable,
        "git_head": _git_head(),
        "fixed_variables": [
            "Knowledge Base V2",
            "BGEEmbedding BAAI/bge-small-zh",
            "KeywordRetriever",
            "VectorRetriever",
            "HybridRetriever 0.5/0.5",
            "Query Rewrite",
            "Top-K=5",
            "min_rerank_score=0.1",
            "Chunk strategy",
            "Gate v3",
        ],
        "baseline_formula": BASELINE_FORMULA,
        "reranker_v2_formula": V2_FORMULA,
        "development_selection_rule": DEVELOPMENT_SELECTION_RULE,
        "baseline": baseline,
        "reranker_v2": reranker_v2,
        "comparison": comparison,
    }


def load_positive_challenge_cases(path: str | Path = CHALLENGE_PATH) -> list[dict]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    return [case for case in cases if case.get("label") == "need_rag"]


def evaluate_variant(name: str, reranker, cases: list[dict]) -> dict:
    pipeline = build_bge_pipeline(reranker)
    case_results = []
    for case in cases:
        normalized_case = normalize_case_for_retrieval(case)
        gate_result = evaluate_retrieval_need(event=case["event"])
        retrieval = (
            pipeline.retrieve(case["event"], top_k=TOP_K).to_dict()
            if gate_result["need_rag"]
            else _empty_retrieval_result()
        )
        metrics = evaluate_retrieval_case(normalized_case, retrieval)
        case_results.append(
            {
                **normalized_case,
                "event": case["event"],
                "gate": gate_result,
                "retrieval": retrieval,
                "metrics": metrics,
            }
        )

    summary = summarize_subset(case_results)
    gate_rejected_cases = [
        case["id"] for case in case_results if not case["gate"].get("need_rag")
    ]
    return {
        "name": name,
        "metric_scope": EVALUATION_SCOPE,
        "summary": {
            **summary,
            "gate_rejected_positive_count": len(gate_rejected_cases),
            "gate_rejected_positive_ids": gate_rejected_cases,
            "acceptable_top1_count": _acceptable_top_k_count(case_results, 1),
            "acceptable_top3_count": _acceptable_top_k_count(case_results, 3),
            "pollution_case_count": sum(
                1 for case in case_results
                if case["metrics"].get("context_pollution_rate", 0.0) > 0
            ),
            "wrong_rank_distribution": count_wrong_by_rank(case_results),
            "confusion_pairs": count_confusion_pairs(case_results),
        },
        "case_results": case_results,
    }


def build_bge_pipeline(reranker) -> RagPipelineRetriever:
    from backend.rag.embeddings.bge_embedding import BGEEmbeddingModel

    bge_model = BGEEmbeddingModel(model_name=BGE_MODEL_NAME)
    vector_retriever = VectorRetriever(embedding_model=bge_model)
    return RagPipelineRetriever(
        hybrid_retriever=HybridRetriever(
            keyword_retriever=KeywordRetriever(),
            vector_retriever=vector_retriever,
        ),
        reranker=reranker,
        min_rerank_score=MIN_RERANK_SCORE,
    )


def compare_variants(baseline: dict, reranker_v2: dict) -> dict:
    baseline_cases = {case["id"]: case for case in baseline["case_results"]}
    v2_cases = {case["id"]: case for case in reranker_v2["case_results"]}
    corrected = []
    newly_promoted_wrong = []
    recall_regressions = []

    for case_id, baseline_case in baseline_cases.items():
        v2_case = v2_cases[case_id]
        baseline_wrong = _wrong_sources(baseline_case)
        v2_wrong = _wrong_sources(v2_case)
        corrected_sources = sorted(baseline_wrong - v2_wrong)
        new_wrong_sources = sorted(v2_wrong - baseline_wrong)
        if corrected_sources:
            corrected.append(
                {
                    "case_id": case_id,
                    "category": baseline_case["category"],
                    "corrected_sources": corrected_sources,
                }
            )
        if new_wrong_sources:
            newly_promoted_wrong.append(
                {
                    "case_id": case_id,
                    "category": baseline_case["category"],
                    "new_wrong_sources": new_wrong_sources,
                }
            )
        if (
            baseline_case["metrics"]["recall_at_3"] or 0.0
        ) > (v2_case["metrics"]["recall_at_3"] or 0.0):
            recall_regressions.append(
                {
                    "case_id": case_id,
                    "category": baseline_case["category"],
                    "baseline_sources": baseline_case["metrics"]["retrieved_sources"],
                    "v2_sources": v2_case["metrics"]["retrieved_sources"],
                }
            )

    v2_summary = reranker_v2["summary"]
    selection_checks = {
        "recall_at_3": (
            v2_summary["recall_at_3"]
            >= DEVELOPMENT_SELECTION_RULE["recall_at_3_min"]
        ),
        "context_pollution_rate": (
            v2_summary["context_pollution_rate"]
            < baseline["summary"]["context_pollution_rate"]
        ),
        "source_category_match": (
            v2_summary["source_category_match"]
            > baseline["summary"]["source_category_match"]
        ),
        "no_recall_regressions": len(recall_regressions) == 0,
    }
    return {
        "metric_differences": metric_differences(baseline["summary"], reranker_v2["summary"]),
        "corrected_wrong_candidates": corrected,
        "newly_promoted_wrong_candidates": newly_promoted_wrong,
        "recall_regression_cases": recall_regressions,
        "selection_checks": selection_checks,
        "candidate_freeze_recommended": all(selection_checks.values()),
    }


def metric_differences(baseline: dict, candidate: dict) -> dict:
    metrics = [
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_1",
        "precision_at_3",
        "precision_at_5",
        "mrr",
        "source_category_match",
        "context_pollution_rate",
        "acceptable_top1_count",
        "acceptable_top3_count",
        "pollution_case_count",
    ]
    return {
        metric: round((candidate.get(metric) or 0.0) - (baseline.get(metric) or 0.0), 4)
        for metric in metrics
    }


def count_wrong_by_rank(case_results: list[dict]) -> dict:
    counts = Counter()
    for case in case_results:
        acceptable_sources = set(case.get("acceptable_sources", []))
        for rank, source in enumerate(case["metrics"]["retrieved_sources"], start=1):
            if source not in acceptable_sources:
                counts[f"rank{rank}"] += 1
    return {f"rank{rank}": counts.get(f"rank{rank}", 0) for rank in range(1, TOP_K + 1)}


def count_confusion_pairs(case_results: list[dict]) -> dict:
    counts = Counter()
    for case in case_results:
        acceptable_sources = set(case.get("acceptable_sources", []))
        for source in case["metrics"]["retrieved_sources"]:
            if source not in acceptable_sources:
                counts[f"{case['category']}->{SOURCE_CATEGORY.get(source, 'unknown')}"] += 1
    return dict(counts.most_common())


def save_report(result: dict, path: str | Path = REPORT_PATH) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_markdown_report(result), encoding="utf-8")
    return output


def build_markdown_report(result: dict) -> str:
    baseline = result["baseline"]["summary"]
    candidate = result["reranker_v2"]["summary"]
    comparison = result["comparison"]
    scope = result["metric_scope"]
    canonical = result["canonical_challenge_v3_metrics"]
    phase4a_scope = result["phase4a_pollution_audit_scope"]
    definitions = result["metric_definitions"]
    lines = [
        "# Domain-Aware RuleBasedReranker Development",
        "",
        "## Scope",
        "",
        f"- experiment: `{result['experiment']}`",
        f"- dataset: `{result['dataset']}`",
        f"- scope: `{result['scope']}`",
        f"- challenge_v3_status: `{result['challenge_v3_status']}`",
        f"- git_head: `{result['git_head']}`",
        "- Challenge v3 has already been used; this report is not independent holdout validation.",
        "- A future frozen retrieval holdout is required before claiming generalization.",
        "- No evaluation gold category or acceptable_sources are passed into the production reranker.",
        "- Phase 4B metrics are `positive-only`, `Gate-applied`, and `source-deduped`.",
        "- Only Phase 4B baseline and Reranker v2 metrics in this report are directly comparable.",
        "",
        "## Metric Scope Metadata",
        "",
        f"- evaluation_scope: `{scope['evaluation_scope']}`",
        f"- dataset_scope: `{scope['dataset_scope']}`",
        f"- total_cases: `{scope['total_cases']}`",
        f"- gate_applied: `{scope['gate_applied']}`",
        f"- gate_version: `{scope['gate_version']}`",
        f"- dedupe_level: `{scope['dedupe_level']}`",
        f"- retrieval_unit: `{scope['retrieval_unit']}`",
        f"- case_set_status: `{scope['case_set_status']}`",
        f"- direct_comparison_allowed: `{scope['direct_comparison_allowed']}`",
        "",
        "## Historical Metric Scopes",
        "",
        "### A. Challenge v3 Canonical E2E",
        "",
        f"- scope: `{canonical['scope']}`",
        f"- gate_applied: `{canonical['gate_applied']}`",
        f"- dedupe_level: `{canonical['dedupe_level']}`",
        f"- purpose: `{canonical['purpose']}`",
        "- NOT DIRECTLY COMPARABLE to Phase 4B positive-only metrics.",
        f"- Recall@1/3/5: `{canonical['recall_at_1']} / {canonical['recall_at_3']} / {canonical['recall_at_5']}`",
        f"- Precision@1/3/5: `{canonical['precision_at_1']} / {canonical['precision_at_3']} / {canonical['precision_at_5']}`",
        f"- MRR: `{canonical['mrr']}`",
        f"- No-hit Accuracy: `{canonical['no_hit_accuracy']}`",
        f"- Source Category Match: `{canonical['source_category_match']}`",
        f"- Context Pollution: `{canonical['context_pollution_rate']}`",
        "",
        "### B. Phase 4B Reranker Development",
        "",
        "- scope: `Challenge v3 Positive 20 cases only`",
        "- Gate applied: `true`",
        "- source dedupe: `true`",
        "- valid comparison: `Baseline old Reranker -> Reranker v2`",
        "",
        "### C. Phase 4A Pollution Audit",
        "",
        f"- scope: `{phase4a_scope['scope']}`",
        f"- gate_applied: `{phase4a_scope['gate_applied']}`",
        f"- dedupe_level: `{phase4a_scope['dedupe_level']}`",
        f"- retrieval_unit: `{phase4a_scope['retrieval_unit']}`",
        f"- purpose: `{phase4a_scope['purpose']}`",
        "- Phase 4A wrong-rank distribution must not be compared directly with Phase 4B source-level wrong-rank.",
        "",
        "## Metric Definitions",
        "",
        "### Precision@K",
        "",
        f"- per_case: `{definitions['precision_at_k']['per_case']}`",
        f"- aggregation: `{definitions['precision_at_k']['aggregation']}`",
        f"- note: {definitions['precision_at_k']['note']}",
        "",
        "### Source Category Match",
        "",
        f"- per_case: `{definitions['source_category_match']['per_case']}`",
        f"- aggregation: `{definitions['source_category_match']['aggregation']}`",
        "",
        "### Context Pollution",
        "",
        f"- per_case: `{definitions['context_pollution_rate']['per_case']}`",
        f"- aggregation: `{definitions['context_pollution_rate']['aggregation']}`",
        f"- valid_comparison: {definitions['context_pollution_rate']['valid_comparison']}",
        "",
        "### Gate-Rejected Positive",
        "",
        f"- case_id: `{definitions['gate_rejected_positive']['case_id']}`",
        f"- behavior: {definitions['gate_rejected_positive']['behavior']}",
        f"- metric_effect: {definitions['gate_rejected_positive']['metric_effect']}",
        "",
        "### Wrong Rank",
        "",
        f"- Phase 4A: `{definitions['wrong_rank']['phase4a']}`",
        f"- Phase 4B: `{definitions['wrong_rank']['phase4b']}`",
        f"- note: {definitions['wrong_rank']['note']}",
        "",
        "## Fixed Variables",
        "",
    ]
    lines.extend(f"- `{item}`" for item in result["fixed_variables"])
    lines.extend(
        [
            "",
            "## Formulas",
            "",
            f"- baseline: `{result['baseline_formula']}`",
            f"- reranker_v2: `{result['reranker_v2_formula']}`",
            "- domain-aware feature: query/chunk coarse domain consistency inferred from production text fields.",
            "",
            "## Metric Comparison",
            "",
            "| Metric | Baseline | Reranker v2 | Difference |",
            "|---|---:|---:|---:|",
        ]
    )
    for metric, diff in comparison["metric_differences"].items():
        lines.append(
            f"| {metric} | `{baseline.get(metric)}` | `{candidate.get(metric)}` | `{diff}` |"
        )
    lines.extend(
        [
            "",
            "## Wrong-Category Rank Distribution",
            "",
            f"- baseline: `{baseline['wrong_rank_distribution']}`",
            f"- reranker_v2: `{candidate['wrong_rank_distribution']}`",
            "",
            "## Cross-Domain Confusion",
            "",
            f"- baseline: `{baseline['confusion_pairs']}`",
            f"- reranker_v2: `{candidate['confusion_pairs']}`",
            "",
            "## Behavior Audit",
            "",
            f"- corrected_wrong_candidates: `{comparison['corrected_wrong_candidates']}`",
            f"- newly_promoted_wrong_candidates: `{comparison['newly_promoted_wrong_candidates']}`",
            f"- recall_regression_cases: `{comparison['recall_regression_cases']}`",
            "",
            "## Development Selection Rule",
            "",
            f"- rule: `{result['development_selection_rule']}`",
            "- rule interpretation: `Recall@3 >= 0.90; v2 Context Pollution < same-scope Baseline; v2 Source Category Match > same-scope Baseline; no large retrieval miss.`",
            f"- checks: `{comparison['selection_checks']}`",
            f"- candidate_freeze_recommended: `{comparison['candidate_freeze_recommended']}`",
            "",
            "## Change Attribution",
            "",
            "- Architecture / scoring feature changes: added query/chunk domain consistency as a soft rerank feature and changed score weights.",
            "- Domain keyword / signal expansion: added coarse domain signal groups for five crisis domains.",
            "- The improvement is rule-based and keyword/signal driven; it is not a learned model.",
            "",
            "## Risks",
            "",
            "- Domain signals are still hand-written and may miss implicit or novel wording.",
            "- Multi-domain incidents are kept soft/neutral, so some cross-domain pollution may remain.",
            "- Challenge v3 is post-hoc development data; a new frozen holdout is required.",
        ]
    )
    return "\n".join(lines) + "\n"


def _baseline_rerank_chunk(query: str, chunk: RetrievedChunk) -> RetrievedChunk:
    title_score = _keyword_overlap_score(query, chunk.title)
    source_score = _baseline_source_match_score(query, chunk.source)
    overlap_score = _keyword_overlap_score(query, chunk.text)
    rerank_score = (
        0.5 * chunk.score
        + 0.2 * title_score
        + 0.15 * source_score
        + 0.15 * overlap_score
    )
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "title_match_score": round(title_score, 4),
            "source_match_score": round(source_score, 4),
            "keyword_overlap_score": round(overlap_score, 4),
        }
    )
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=round(rerank_score, 4),
    )


def _keyword_overlap_score(query: str, text: str) -> float:
    from backend.rag.reranker import _keyword_overlap_score as overlap

    return overlap(query, text)


def _baseline_source_match_score(query: str, source: str) -> float:
    from backend.rag.reranker import _SOURCE_HINTS

    for keyword, expected_source in _SOURCE_HINTS.items():
        if keyword in query and expected_source == source:
            return 1.0
    return 0.0


def _format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{chunk.source} | score={chunk.score} | rerank_score={chunk.rerank_score}]\n{chunk.text}"
        for chunk in chunks
    )


def _source_dict(chunk: RetrievedChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "source": chunk.source,
        "title": chunk.title,
        "score": chunk.score,
        "rerank_score": chunk.rerank_score,
    }


def _empty_retrieval_result() -> dict:
    return {
        "context": "",
        "chunks": [],
        "sources": [],
    }


def _acceptable_top_k_count(case_results: list[dict], k: int) -> int:
    count = 0
    for case in case_results:
        acceptable_sources = set(case.get("acceptable_sources", []))
        if acceptable_sources & set(case["metrics"]["retrieved_sources"][:k]):
            count += 1
    return count


def _wrong_sources(case: dict) -> set[str]:
    acceptable_sources = set(case.get("acceptable_sources", []))
    return {
        source for source in case["metrics"]["retrieved_sources"]
        if source not in acceptable_sources
    }


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    evaluation_result = run_development_evaluation()
    report_path = save_report(evaluation_result)
    print(json.dumps(evaluation_result["comparison"], ensure_ascii=False, indent=2))
    print(f"report={report_path}")
