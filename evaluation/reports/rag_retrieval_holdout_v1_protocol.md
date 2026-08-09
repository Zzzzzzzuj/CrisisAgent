# Reranker v2 Frozen Retrieval Holdout v1 Protocol

## Purpose

This holdout validates only one question:

Can `Domain-Aware RuleBasedReranker v2` reduce cross-domain Context Pollution while preserving Recall, compared with the old `RuleBasedReranker`?

This is a Retriever isolation test. Retrieval Need Gate is intentionally not applied here because Gate v3 already has its own frozen Challenge v3 validation. This holdout must not be used to evaluate end-to-end Gate + Retriever behavior.

## Dataset

- dataset: `evaluation/rag_retrieval_holdout_v1.json`
- total_cases: `30`
- positive_retrieval_cases: `30`
- negative_or_unrelated_cases: `0`
- expected_retrieval: `true` for every case
- categories:
  - `food_safety`: `6`
  - `data_privacy`: `6`
  - `service_outage`: `6`
  - `product_quality`: `6`
  - `executive_misconduct`: `6`

## Source Label Schema

Each case defines three mutually exclusive source groups:

- `acceptable_sources`: source documents that directly support the case category and should count as relevant retrieval hits.
- `neutral_sources`: generic support documents that may be useful but should not count as either acceptable hits or cross-domain pollution.
- `forbidden_sources`: specialized source documents from other business domains that should count as cross-domain pollution for this case.

For this holdout:

- specialized domain source examples: `food_safety.md`, `data_privacy.md`, `service_outage.md`, `product_quality.md`, `executive_misconduct.md`
- generic neutral source examples: `crisis_response.md`, `legal_risk_rules.md`

The labels are assigned from Knowledge Base V2 category semantics, not from model predictions.

## Cross-Domain Boundary Coverage

The holdout includes realistic crisis events designed to stress these confusion boundaries:

- `food_safety` vs `product_quality`
- `data_privacy` vs `service_outage`
- `service_outage` vs `product_quality`
- `product_quality` vs `food_safety`
- `executive_misconduct` vs generic crisis response

It also includes:

- short queries
- long queries
- implicit crisis descriptions
- general crisis words shared across domains
- some multi-domain wording

## Metric Scope

- evaluation_scope: `positive-only`
- total_cases: `30`
- Gate applied: `false`
- dedupe_level: `source`
- retrieval_unit: `deduped source document`
- top_k values: `1`, `3`, `5`
- only variable under test: `Reranker`

Old Reranker and Reranker v2 must use exactly the same:

- query
- candidate pool
- Knowledge Base V2
- Keyword Retriever
- BGE Vector Retriever
- Hybrid Retriever `0.5 / 0.5`
- Query Rewrite
- Top-K
- min rerank threshold
- source dedupe
- metric formulas

## Metric Definitions

### Recall@K

Per case:

```text
Recall@K = len(set(top_k_deduped_sources) & set(acceptable_sources))
           / len(set(acceptable_sources))
```

Macro aggregation:

```text
mean(case Recall@K over 30 positive retrieval cases)
```

### Precision@K

Per case:

```text
Precision@K = len(set(top_k_deduped_sources) & set(acceptable_sources)) / K
```

Macro aggregation:

```text
mean(case Precision@K over 30 positive retrieval cases)
```

Neutral sources do not count as precision hits.

### MRR

Per case:

```text
MRR case score = 1 / rank_of_first_acceptable_source
```

If no acceptable source is retrieved, the case score is `0`.

Macro aggregation:

```text
mean(case reciprocal rank over 30 positive retrieval cases)
```

### Source Category Match

Per case:

```text
acceptable_count = number of retrieved deduped sources in acceptable_sources
forbidden_count = number of retrieved deduped sources in forbidden_sources

SCM = acceptable_count / (acceptable_count + forbidden_count)
```

Neutral sources are excluded from both numerator and denominator.

If `acceptable_count + forbidden_count = 0`, then:

```text
SCM = 0
```

This prevents empty retrieval from receiving an artificially good category-match score.

### Context Pollution

Per case:

```text
forbidden_count = number of retrieved deduped sources in forbidden_sources
neutral_count = number of retrieved deduped sources in neutral_sources
acceptable_count = number of retrieved deduped sources in acceptable_sources

Context Pollution = forbidden_count
                    / (acceptable_count + neutral_count + forbidden_count)
```

If no source is retrieved:

```text
Context Pollution = 0
```

However, empty retrieval must still hurt Recall, MRR, and SCM. It must not be treated as a successful low-pollution retrieval strategy.

## Primary Validation Criteria

These criteria are frozen before the first Old vs v2 run. They are project engineering criteria, not industry standards.

Reranker v2 PASS requires all of the following:

1. `v2 Recall@3 >= 0.90`
2. `v2 Recall@3` must not drop more than `0.05` below Old Reranker baseline Recall@3.
3. `v2 Context Pollution` must be lower than Old Reranker baseline Context Pollution.
4. Relative pollution reduction must be at least `20%`:

```text
(baseline_pollution - v2_pollution) / baseline_pollution >= 0.20
```

5. `v2 Source Category Match` must be higher than Old Reranker baseline Source Category Match.
6. New Top3 retrieval regression cases must be `<= 2`.

Definition of new Top3 retrieval regression:

```text
Old Reranker Top3 contains at least one acceptable source,
but Reranker v2 Top3 contains no acceptable source.
```

7. Every category Recall@3 must be `>= 0.75`.

## Secondary Metrics

These must be reported but are not hard PASS criteria:

- Recall@1
- Recall@5
- Precision@1
- Precision@3
- Precision@5
- MRR
- Top1 acceptable count
- Top3 acceptable count
- pollution case count
- wrong-category rank distribution
- cross-domain confusion pairs

## Freeze Rules

After the first formal Old Reranker vs Reranker v2 run:

- Retrieval Holdout v1 is no longer untouched.
- The dataset must not be edited and rerun as an independent validation set.
- If the result is FAIL, keep the FAIL result.
- If Reranker is modified later, a new frozen retrieval holdout is required.

## Data Leakage Rules

Before the first evaluation run, do not:

- run Old Reranker on this holdout
- run Reranker v2 on this holdout
- run BGE retrieval on this holdout
- run a retrieval evaluator on this holdout
- calculate retrieval metrics
- change cases based on predictions

Allowed static checks:

- schema validation
- count validation
- ID uniqueness
- exact event duplicate checks against prior datasets

## Status

- Gate run before freeze: `no`
- Old Reranker run before freeze: `no`
- Reranker v2 run before freeze: `no`
- BGE run before freeze: `no`
- Retrieval metrics calculated before freeze: `no`
