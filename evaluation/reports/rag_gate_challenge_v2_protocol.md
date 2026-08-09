# CrisisAgent Retrieval Need Gate Challenge v2 Protocol

## Purpose

This protocol freezes `evaluation/rag_gate_challenge_v2.json` before the first Gate v2 Challenge Evaluation run.

Gate v2 has already been developed as a Conservative Reject Gate:

- Recall-first behavior.
- Only high-confidence non-crisis intent rejects RAG.
- Ambiguous enterprise risk defaults to `need_rag=true`.

Challenge v1 can only be used as post-hoc regression because Gate v2 was designed after seeing its first-run failure. Challenge v2 is created as a new untouched holdout for independent validation.

## Dataset

- Dataset file: `evaluation/rag_gate_challenge_v2.json`
- Total samples: `40`
- Positive crisis samples: `20`
- Negative samples: `20`

## Distribution

### Positive Crisis

- `food_safety`: `4`
- `data_privacy`: `4`
- `service_outage`: `4`
- `product_quality`: `4`
- `executive_misconduct`: `4`

Positive cases intentionally include weak explicit keywords, implicit user harm, implicit service/data/product risks, longer text, mixed business context, and cases without direct terms such as "曝光", "投诉", "泄露", "宕机", "召回", or "监管".

### Negative

- `unrelated`: `4`
- `business_non_crisis`: `4`
- `hard_negative`: `12`

Hard negatives intentionally increase from v1 because Gate v2's known risk is false positive behavior on topic-relevant but non-crisis intent.

The hard-negative intent coverage is:

- `historical_analysis`
- `statistics_or_reporting`
- `preparedness_drill`
- `future_hypothetical`
- `policy_learning`
- `content_editing`
- `lookup`
- `customer_service`
- `template_writing`
- `trend_analysis`

## Evaluation-Only Fields

The following fields are labels or audit metadata and must not be used by production Gate logic:

- `label`
- `type`
- `category`
- `notes`
- `weak_explicit_crisis`
- `intent_type`

Production Gate logic may only use production-available input text and explicitly allowed runtime context.

## Prohibited Use

This Challenge Set must not be used to:

- Modify Retrieval Need Gate rules.
- Tune retrieval thresholds.
- Modify Knowledge Base content.
- Tune Hybrid Retriever weights.
- Tune Reranker behavior.
- Tune Embedding behavior.
- Modify query rewrite rules.
- Modify Legal Agent, Runtime, Agent prompts, or API behavior.

Before the first formal Challenge Evaluation, do not:

- Run `retrieval_need_gate.py` against this dataset.
- Run any Gate evaluator on this dataset.
- Run BGE retrieval on this dataset.
- Compute TPR, TNR, accuracy, decision scores, or predictions for this dataset.
- Rewrite samples based on prediction behavior.

Allowed pre-freeze checks are limited to JSON parsing, schema checks, ID uniqueness, distribution counts, and exact duplicate checks.

## Pre-Registered Acceptance Criteria

These are project engineering targets, not industry benchmarks.

### Gate Metrics

- Positive TPR must be `>= 0.90`.
- Negative TNR must be `>= 0.85`.
- Hard Negative Reject Rate must be `>= 0.75`.
- Gate FN must be `<= 2 / 20`.
- Hard Negative must reject at least `9 / 12`.
- No positive crisis category may have TPR below `0.75`.

The hard-negative target is set to `0.75` because Gate v2 is intentionally recall-first. Limited false positives are acceptable, but the Gate must not systematically pass topic-relevant non-crisis intent.

### End-to-End Metrics

- BGE + Gate Recall@3 must be `>= 0.63`.
- No-hit Accuracy must be `>= 0.85`.
- Context Pollution Rate must be reported.
- The system must not accept severe Positive Recall loss merely to improve No-hit Accuracy.

The `0.63` Recall@3 threshold comes from the Development BGE Recall@3 of `0.70`, with about 10% relative loss allowed as this project's engineering criterion. It is not an industry standard.

## Data Freeze Rule

After the first formal Gate v2 Challenge Evaluation:

- `rag_gate_challenge_v2.json` permanently loses untouched status.
- Results must be recorded as-is, whether PASS or FAIL.
- The dataset must not be edited and rerun as if it were still independent.
- If Gate v2 fails, later Gate changes require a new Challenge v3 or another truly untouched holdout.

## Scope Notes

- Challenge v1 first formal result was FAIL and remains part of project history.
- Gate v2 results on Challenge v1 are post-hoc regression only.
- Challenge v2 is intended to test whether Gate v2 generalizes beyond Development, Calibration, and Challenge v1 analysis.
