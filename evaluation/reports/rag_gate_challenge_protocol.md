# CrisisAgent Retrieval Need Gate Challenge Protocol

## Purpose

This protocol freezes `evaluation/rag_gate_challenge_v1.json` before the first Challenge Evaluation run.

The dataset is used only to validate whether the Retrieval Need Gate generalizes beyond the Development + Calibration data used in Phase 3D-1.

## Dataset

- Dataset file: `evaluation/rag_gate_challenge_v1.json`
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

### Negative

- `unrelated`: `5`
- `business_non_crisis`: `5`
- `hard_negative`: `10`

## Allowed Use

This dataset may be used only for Retrieval Need Gate generalization validation.

The following fields are evaluation-only labels and must not be used by production Gate logic:

- `label`
- `type`
- `category`
- `notes`
- `weak_explicit_crisis`

Production Gate logic may only use the event text and any production-available optional context explicitly allowed by the production integration design.

## Prohibited Use

This Challenge Set must not be used to:

- Modify Retrieval Need Gate rules.
- Tune retrieval thresholds.
- Modify the Knowledge Base.
- Tune Hybrid Retriever weights.
- Tune the Reranker.
- Tune Embedding behavior.
- Select or tune BGE / Hash behavior.
- Modify query rewrite rules.

The first formal Challenge Evaluation must be recorded as-is. If the result is PASS or FAIL, `rag_gate_challenge_v1.json` must not be edited and rerun as if it were still untouched.

If the Gate fails, record the failure honestly. Later Gate changes require a new Challenge Set such as `rag_gate_challenge_v2.json` or another truly untouched holdout.

## Pre-Registered Acceptance Criteria

### Gate Metrics

- Positive TPR must be `>= 0.90`.
- Negative TNR must be `>= 0.85`.
- Hard Negative Reject Rate must be `>= 0.80`.
- No positive crisis category may be rejected at large scale.

### End-to-End Metrics

- BGE + Gate Recall@3 must be `>= 0.63`.
- No-hit Accuracy must be `>= 0.85`.
- Context Pollution Rate must be reported.
- The system must not accept severe Positive Recall loss merely to improve No-hit Accuracy.

The `0.63` Recall@3 threshold comes from the current Development BGE Recall@3 of `0.70`, with about 10% relative loss allowed as a project engineering criterion. It is not an industry benchmark.

## Important Scope Notes

- Phase 3D-1 Development + Calibration data already participated in Gate analysis and cannot prove final generalization.
- The 24 negative calibration cases are not an untouched final test set.
- This Challenge Set must be frozen before any Gate prediction is run against it.
- Phase 3D Challenge metrics must not be used to retroactively modify this v1 dataset.

## First-Run Rule

Before the first Challenge Evaluation:

- Do not run `retrieval_need_gate.py` against this dataset.
- Do not run a Gate evaluator against this dataset.
- Do not compute TPR, TNR, accuracy, or predictions for this dataset.
- Do not run BGE retrieval for this dataset.

After the first Challenge Evaluation:

- Keep the dataset unchanged.
- Record all false positives and false negatives.
- If the Gate fails, create a new versioned Challenge Set only after recording the v1 failure.
