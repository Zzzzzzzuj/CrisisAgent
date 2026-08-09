# CrisisAgent Retrieval Need Gate Challenge v3 Protocol

## Purpose

This protocol freezes `evaluation/rag_gate_challenge_v3.json` before the first Gate v3 Challenge Evaluation run.

Gate history is preserved as follows:

- Gate v1 Challenge v1 FIRST RUN: `FAIL`.
- Gate v2 Challenge v2 FIRST RUN: `FAIL`.
- Gate v3 results on Challenge v1/v2 are `post-hoc regression only`.

Challenge v3 is a new untouched holdout for Gate v3. It is designed to test whether the two-layer gate can distinguish a real current incident from topic-relevant non-current tasks.

## Dataset

- Dataset file: `evaluation/rag_gate_challenge_v3.json`
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

Positive cases focus on Current Incident Detector false-negative risk. They include weak current-incident wording, real current incidents mixed with task words, long mixed contexts, and negation such as "原因尚未确认" where the incident itself has already happened.

Static design counts:

- Weak current-incident positives: at least `12 / 20`.
- Current incident + task-word positives: at least `12 / 20`.

### Negative

- `unrelated`: `4`
- `business_non_crisis`: `4`
- `hard_negative`: `12`

Hard negatives are topic-relevant but non-current tasks. They cover:

- `preparedness`
- `historical_analysis`
- `statistics_reporting`
- `training_learning`
- `content_editing`
- `policy_learning`
- `lookup`
- `customer_service`
- `future_hypothetical`
- `template_writing`
- `trend_analysis`

The hard-negative set intentionally uses high-risk topic words such as failure, data leakage, overheating, food complaints, recall, and executive controversy, while making the task historical, future, training, template, drill, learning, statistics, or lookup oriented.

## Evaluation-Only Fields

The following fields are labels or audit metadata and must not be used by production Gate logic:

- `label`
- `type`
- `category`
- `notes`
- `weak_current_incident`
- `current_incident_with_task_word`
- `intent_type`

Production Gate logic may only use production-available input text and explicitly allowed runtime context.

## Prohibited Use Before First Evaluation

Before the first formal Challenge v3 Evaluation, do not:

- Run Gate v3 on this dataset.
- Run a Gate evaluator on this dataset.
- Run BGE retrieval on this dataset.
- Inspect prediction, decision score, or decision path.
- Rewrite samples based on Gate behavior.
- Modify Gate rules, RAG parameters, Knowledge Base, Hybrid weights, Reranker, Embedding, Prompt, Agent, Runtime, or API based on this dataset.

Allowed pre-freeze checks are limited to:

- JSON parsing.
- Schema validation.
- ID uniqueness.
- Count and distribution checks.
- Exact duplicate checks against v1, v2, calibration, and RAG v2 cases.

## Pre-Registered Acceptance Criteria

These are project engineering targets, not industry benchmarks. They are frozen before the first Challenge v3 prediction.

### Gate Metrics

- Positive TPR must be `>= 0.90`.
- Negative TNR must be `>= 0.85`.
- Hard Negative Reject Rate must be `>= 0.75`.
- Gate FN must be `<= 2 / 20`.
- Hard Negative must reject at least `9 / 12`.
- No positive crisis category may have TPR below `0.75`.

### End-to-End Metrics

- BGE + Gate Recall@3 must be `>= 0.63`.
- No-hit Accuracy must be `>= 0.85`.
- Context Pollution Rate must be reported.

The `0.63` Recall@3 threshold follows the same project engineering criterion used in Challenge v2: it allows about 10% relative loss from Development BGE Recall@3=`0.70`. It is not an industry standard.

## Additional Observation Metrics

The following metrics must be recorded but are not hard PASS criteria in v3:

- `current_incident_positive_pass_rate`
- `non_current_hard_negative_reject_rate`

They are included to understand whether the two-layer architecture is working as intended. They must not be promoted to PASS criteria after seeing results.

## Data Freeze Rule

After the first formal Gate v3 Challenge Evaluation:

- `rag_gate_challenge_v3.json` permanently loses untouched status.
- Results must be recorded as-is, whether PASS or FAIL.
- Challenge v3 must not be edited and rerun as if it were still independent.
- If Gate v3 fails, later Gate changes require a new Challenge v4 or another truly untouched holdout.

## Scope Notes

- Challenge v1 and Challenge v2 remain project history and post-hoc diagnostic datasets only.
- Challenge v3 is intended to test Gate v3 generalization beyond Development, Calibration, Challenge v1 post-hoc, and Challenge v2 post-hoc analysis.
- This protocol does not approve changing Legal Agent, workflow, executor, adapter, Retriever, Knowledge Base, Embedding, Hybrid, Reranker, threshold, Top-K, Chunk, Prompt, or Runtime.
