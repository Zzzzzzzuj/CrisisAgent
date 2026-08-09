# Domain-Aware RuleBasedReranker Development

## Scope

- experiment: `Domain-Aware RuleBasedReranker Development`
- dataset: `evaluation\rag_gate_challenge_v3.json`
- scope: `post-hoc development only`
- challenge_v3_status: `no longer untouched`
- git_head: `8336085`
- Challenge v3 has already been used; this report is not independent holdout validation.
- A future frozen retrieval holdout is required before claiming generalization.
- No evaluation gold category or acceptable_sources are passed into the production reranker.
- Phase 4B metrics are `positive-only`, `Gate-applied`, and `source-deduped`.
- Only Phase 4B baseline and Reranker v2 metrics in this report are directly comparable.

## Metric Scope Metadata

- evaluation_scope: `positive_only`
- dataset_scope: `Challenge v3 positive cases only`
- total_cases: `20`
- gate_applied: `True`
- gate_version: `Gate v3`
- dedupe_level: `source`
- retrieval_unit: `deduped source document`
- case_set_status: `post-hoc development only`
- direct_comparison_allowed: `baseline_vs_reranker_v2_same_scope_only`

## Historical Metric Scopes

### A. Challenge v3 Canonical E2E

- scope: `40 cases: 20 positive + 20 negative`
- gate_applied: `True`
- dedupe_level: `source`
- purpose: `Gate + Retriever overall evaluation`
- NOT DIRECTLY COMPARABLE to Phase 4B positive-only metrics.
- Recall@1/3/5: `0.65 / 0.95 / 0.95`
- Precision@1/3/5: `0.325 / 0.1583 / 0.095`
- MRR: `0.7917`
- No-hit Accuracy: `0.85`
- Source Category Match: `0.4933`
- Context Pollution: `0.3733`

### B. Phase 4B Reranker Development

- scope: `Challenge v3 Positive 20 cases only`
- Gate applied: `true`
- source dedupe: `true`
- valid comparison: `Baseline old Reranker -> Reranker v2`

### C. Phase 4A Pollution Audit

- scope: `Challenge v3 positive cases, chunk-level trace`
- gate_applied: `False`
- dedupe_level: `none`
- retrieval_unit: `chunk`
- purpose: `Locate where pollution first appears across retrieval stages.`
- Phase 4A wrong-rank distribution must not be compared directly with Phase 4B source-level wrong-rank.

## Metric Definitions

### Precision@K

- per_case: `len(set(deduped_retrieved_sources[:k]) & acceptable_sources) / k`
- aggregation: `average over the 20 positive development cases`
- note: Challenge v3 canonical Precision@K averages over 40 cases, so its P@1=0.325 is not directly comparable to Phase 4B positive-only baseline P@1=0.65.

### Source Category Match

- per_case: `matched acceptable deduped sources / retrieved deduped sources; empty retrieval returns 1.0`
- aggregation: `weighted average with weight=max(1, source_count)`

### Context Pollution

- per_case: `forbidden deduped sources or forbidden categories / retrieved deduped sources; empty retrieval returns 0.0`
- aggregation: `weighted average with weight=max(1, source_count)`
- valid_comparison: Phase 4B baseline 0.4314 -> reranker_v2 0.1765 is same-scope and directly comparable; Challenge v3 canonical 0.3733 must not be used as the Phase 4B before value.

### Gate-Rejected Positive

- case_id: `gate_challenge_v3_data_privacy_004`
- behavior: Gate v3 returns need_rag=false, so retrieval is empty.
- metric_effect: Recall@K=0, Precision@K=0, reciprocal_rank=0, source_category_match=1.0, context_pollution_rate=0.0, source_count weight=1.

### Wrong Rank

- Phase 4A: `chunk-level, non-deduped, no Gate`
- Phase 4B: `source-level, deduped, Gate-applied`
- note: Phase 4A rank distribution must not be compared directly with Phase 4B wrong-rank distribution. Phase 4B baseline and v2 can be compared because they share one evaluator.

## Fixed Variables

- `Knowledge Base V2`
- `BGEEmbedding BAAI/bge-small-zh`
- `KeywordRetriever`
- `VectorRetriever`
- `HybridRetriever 0.5/0.5`
- `Query Rewrite`
- `Top-K=5`
- `min_rerank_score=0.1`
- `Chunk strategy`
- `Gate v3`

## Formulas

- baseline: `0.5 * retrieval_score + 0.2 * title_match + 0.15 * source_match + 0.15 * keyword_overlap`
- reranker_v2: `0.48 * retrieval_score + 0.17 * title_match + 0.10 * source_match + 0.14 * keyword_overlap + domain_adjustment`
- domain-aware feature: query/chunk coarse domain consistency inferred from production text fields.

## Metric Comparison

| Metric | Baseline | Reranker v2 | Difference |
|---|---:|---:|---:|
| recall_at_1 | `0.65` | `0.75` | `0.1` |
| recall_at_3 | `0.95` | `0.95` | `0.0` |
| recall_at_5 | `0.95` | `0.95` | `0.0` |
| precision_at_1 | `0.65` | `0.75` | `0.1` |
| precision_at_3 | `0.3166` | `0.3166` | `0.0` |
| precision_at_5 | `0.19` | `0.19` | `0.0` |
| mrr | `0.7917` | `0.8417` | `0.05` |
| source_category_match | `0.3921` | `0.5882` | `0.1961` |
| context_pollution_rate | `0.4314` | `0.1765` | `-0.2549` |
| acceptable_top1_count | `13` | `15` | `2` |
| acceptable_top3_count | `19` | `19` | `0` |
| pollution_case_count | `17` | `6` | `-11` |

## Wrong-Category Rank Distribution

- baseline: `{'rank1': 6, 'rank2': 14, 'rank3': 10, 'rank4': 1, 'rank5': 0}`
- reranker_v2: `{'rank1': 4, 'rank2': 7, 'rank3': 3, 'rank4': 0, 'rank5': 0}`

## Cross-Domain Confusion

- baseline: `{'food_safety->product_quality': 4, 'service_outage->product_quality': 4, 'data_privacy->service_outage': 3, 'product_quality->data_privacy': 3, 'executive_misconduct->crisis_response': 3, 'food_safety->service_outage': 2, 'service_outage->crisis_response': 2, 'executive_misconduct->data_privacy': 2, 'food_safety->crisis_response': 1, 'food_safety->executive_misconduct': 1, 'data_privacy->legal': 1, 'data_privacy->crisis_response': 1, 'service_outage->data_privacy': 1, 'service_outage->legal': 1, 'product_quality->food_safety': 1, 'product_quality->service_outage': 1}`
- reranker_v2: `{'data_privacy->service_outage': 3, 'executive_misconduct->crisis_response': 3, 'service_outage->crisis_response': 2, 'food_safety->crisis_response': 1, 'food_safety->product_quality': 1, 'data_privacy->legal': 1, 'data_privacy->crisis_response': 1, 'service_outage->product_quality': 1, 'product_quality->data_privacy': 1}`

## Behavior Audit

- corrected_wrong_candidates: `[{'case_id': 'gate_challenge_v3_food_safety_001', 'category': 'food_safety', 'corrected_sources': ['product_quality.md', 'service_outage.md']}, {'case_id': 'gate_challenge_v3_food_safety_002', 'category': 'food_safety', 'corrected_sources': ['product_quality.md', 'service_outage.md']}, {'case_id': 'gate_challenge_v3_food_safety_004', 'category': 'food_safety', 'corrected_sources': ['executive_misconduct.md', 'product_quality.md']}, {'case_id': 'gate_challenge_v3_service_outage_001', 'category': 'service_outage', 'corrected_sources': ['product_quality.md']}, {'case_id': 'gate_challenge_v3_service_outage_003', 'category': 'service_outage', 'corrected_sources': ['data_privacy.md', 'legal_risk_rules.md', 'product_quality.md']}, {'case_id': 'gate_challenge_v3_service_outage_004', 'category': 'service_outage', 'corrected_sources': ['product_quality.md']}, {'case_id': 'gate_challenge_v3_product_quality_001', 'category': 'product_quality', 'corrected_sources': ['data_privacy.md']}, {'case_id': 'gate_challenge_v3_product_quality_002', 'category': 'product_quality', 'corrected_sources': ['data_privacy.md', 'food_safety.md']}, {'case_id': 'gate_challenge_v3_product_quality_003', 'category': 'product_quality', 'corrected_sources': ['service_outage.md']}, {'case_id': 'gate_challenge_v3_executive_misconduct_001', 'category': 'executive_misconduct', 'corrected_sources': ['data_privacy.md']}, {'case_id': 'gate_challenge_v3_executive_misconduct_003', 'category': 'executive_misconduct', 'corrected_sources': ['data_privacy.md']}]`
- newly_promoted_wrong_candidates: `[]`
- recall_regression_cases: `[]`

## Development Selection Rule

- rule: `{'recall_at_3_min': 0.9, 'context_pollution_below': 'same_scope_baseline', 'source_category_match_above': 'same_scope_baseline', 'no_large_retrieval_miss': True}`
- rule interpretation: `Recall@3 >= 0.90; v2 Context Pollution < same-scope Baseline; v2 Source Category Match > same-scope Baseline; no large retrieval miss.`
- checks: `{'recall_at_3': True, 'context_pollution_rate': True, 'source_category_match': True, 'no_recall_regressions': True}`
- candidate_freeze_recommended: `True`

## Change Attribution

- Architecture / scoring feature changes: added query/chunk domain consistency as a soft rerank feature and changed score weights.
- Domain keyword / signal expansion: added coarse domain signal groups for five crisis domains.
- The improvement is rule-based and keyword/signal driven; it is not a learned model.

## Risks

- Domain signals are still hand-written and may miss implicit or novel wording.
- Multi-domain incidents are kept soft/neutral, so some cross-domain pollution may remain.
- Challenge v3 is post-hoc development data; a new frozen holdout is required.
