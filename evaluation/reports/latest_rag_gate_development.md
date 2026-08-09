# CrisisAgent RAG Gate Development Evaluation

## Experiment

- Gate type: `deterministic_retrieval_need_gate`
- Production Legal Agent path changed: `False`
- Old Final Set run: `False`
- BGE model: `BAAI/bge-small-zh`
- min_rerank_score: `0.1`
- positive cases: `15`
- negative cases: `24`
- negative type counts: `{'business_non_crisis': 8, 'hard_negative': 8, 'unrelated': 8}`
- scope: These are Development + Calibration results, not final generalization results.
- calibration note: The 24 negative cases were used during Retrieval Need Gate development analysis.
- challenge set requirement: The next step must validate this Gate on an untouched Challenge Set.
- production note: The Gate has not been integrated into the Legal Agent production path.
- metric note: Phase 3D Context Pollution Rate uses a different evaluation scope than Phase 3C, so do not compute a direct improvement ratio between them.

## Gate Metrics

- TP: `15`
- TN: `24`
- FP: `0`
- FN: `0`
- TPR / Recall: `1.0`
- TNR / Specificity: `1.0`
- FPR: `0.0`
- FNR: `0.0`
- Accuracy: `1.0`
- hard_negative_reject_rate: `1.0`
- business_non_crisis_reject_rate: `1.0`
- unrelated_reject_rate: `1.0`

## End-to-End Comparison

| Metric | BGE without Gate | BGE + Gate |
|---|---:|---:|
| Recall@3 | 0.7 | 0.7 |
| MRR | 1.0 | 1.0 |
| No-hit Accuracy | 0.0 | 1.0 |
| Context Pollution Rate | 0.0488 | 0.0488 |

## False Positives

- None

## False Negatives

- None
