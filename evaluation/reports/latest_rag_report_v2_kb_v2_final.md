# CrisisAgent RAG Evaluation V2 - Knowledge Base V2 Holdout Final

## Experiment Metadata

- experiment: `Knowledge Base V2`
- split: `final`
- frozen_commit: `12aaef4`
- final set used for tuning: `False`
- Retriever unchanged: `True`
- Hybrid retrieval unchanged: `True`
- Embedding unchanged: `True`
- Reranker unchanged: `True`
- Threshold unchanged: `True`
- min_rerank_score: `0.1`
- top_k: `5`

This report measures end-to-end retrieval changes after expanding the knowledge base. It should not be described as a Retriever algorithm improvement because retrieval code and parameters were not changed.

## Final Metrics

- Total cases: `12`
- Hit case count: `10`
- No-hit case count: `2`
- Recall@1: `0.3833`
- Recall@3: `0.4667`
- Recall@5: `0.4667`
- Precision@1: `0.75`
- Precision@3: `0.3055`
- Precision@5: `0.1833`
- MRR: `0.9`
- No-hit Accuracy: `0.5`
- Source Category Match: `0.4444`
- Context Pollution Rate: `0.0741`
- Fallback count: `0`

## Baseline Comparison

| Metric | Baseline Final | KB V2 Final | Absolute Difference | Relative Difference |
|---|---:|---:|---:|---:|
| Recall@1 | 0.20 | 0.3833 | +0.1833 | +91.65% |
| Recall@3 | 0.30 | 0.4667 | +0.1667 | +55.57% |
| Recall@5 | 0.30 | 0.4667 | +0.1667 | +55.57% |
| Precision@1 | 0.25 | 0.75 | +0.50 | +200.00% |
| Precision@3 | 0.1389 | 0.3055 | +0.1666 | +119.94% |
| Precision@5 | 0.0833 | 0.1833 | +0.10 | +120.05% |
| MRR | 0.35 | 0.90 | +0.55 | +157.14% |
| No-hit Accuracy | 1.00 | 0.50 | -0.50 | -50.00% |
| Source Category Match | 0.7333 | 0.4444 | -0.2889 | -39.40% |
| Context Pollution Rate | 0.20 | 0.0741 | -0.1259 | -62.95% |
| Fallback Count | 0 | 0 | 0 | N/A |

The Final Set contains only two unrelated/no-hit cases. One unexpected retrieval changes No-hit Accuracy from `1.0` to `0.5`, so this should be treated as a concrete regression signal for this holdout sample, not as a stable 50% degradation estimate.

## Category Metrics

### data_privacy

- Recall@3: `0.5`
- MRR: `1.0`
- Source Category Match: `0.5`
- Context Pollution Rate: `0.1667`

### executive_misconduct

- Recall@3: `0.75`
- MRR: `1.0`
- Source Category Match: `0.6`
- Context Pollution Rate: `0.0`

### food_safety

- Recall@3: `0.25`
- MRR: `0.5`
- Source Category Match: `0.1429`
- Context Pollution Rate: `0.0`

### product_quality

- Recall@3: `0.3333`
- MRR: `1.0`
- Source Category Match: `0.5`
- Context Pollution Rate: `0.25`

### service_outage

- Recall@3: `0.5`
- MRR: `1.0`
- Source Category Match: `0.6667`
- Context Pollution Rate: `0.0`

### unrelated

- No-hit Accuracy: `0.5`
- Unexpected hit cases: `1`

## Failed Or Polluted Final Cases

### rag_food_safety_final_001

- category: `food_safety`
- query: `门店标签日期和实际制作日期不一致，网友质疑食安风险`
- acceptable_sources: `food_safety.md`, `legal_risk_rules.md`
- actual_sources: `crisis_response.md`, `service_outage.md`, `executive_misconduct.md`
- scores: `0.5`, `0.3333`, `0.3333`, `0.2995`, `0.2751`
- rerank_scores: `0.25`, `0.1666`, `0.1666`, `0.1497`, `0.1376`
- context_pollution: `0.0`
- failure_reason: `wrong_category`

### rag_data_privacy_final_002

- category: `data_privacy`
- query: `订单地址 电话 被陌生人获取 信息安全 排查`
- acceptable_sources: `data_privacy.md`, `legal_risk_rules.md`, `crisis_response.md`
- actual_sources: `data_privacy.md`, `product_quality.md`, `food_safety.md`, `service_outage.md`
- scores: `0.2149`, `0.2137`, `0.1726`, `0.184`, `0.1875`
- rerank_scores: `0.1356`, `0.135`, `0.1082`, `0.1045`, `0.1031`
- context_pollution: `0.25`
- failure_reason: `wrong_category`

### rag_product_quality_final_001

- category: `product_quality`
- query: `运动器材刹车部件松动 消费者担心使用安全`
- acceptable_sources: `product_quality.md`, `legal_risk_rules.md`, `crisis_response.md`
- actual_sources: `product_quality.md`, `food_safety.md`, `data_privacy.md`
- scores: `0.1855`, `0.1898`, `0.1863`
- rerank_scores: `0.1427`, `0.137`, `0.101`
- context_pollution: `0.3333`
- failure_reason: `wrong_category`

### rag_unrelated_final_002

- category: `unrelated`
- query: `发票抬头填写错误 想要重新开票`
- acceptable_sources: none
- actual_sources: `service_outage.md`
- scores: `0.2115`
- rerank_scores: `0.1057`
- context_pollution: `0.0`
- failure_reason: `unexpected_hit`

## Notes

- `service_outage` improved from baseline Recall@3 `0` to KB V2 Recall@3 `0.5`.
- `product_quality` now retrieves `product_quality.md` in Final, but still has cross-domain pollution.
- `data_privacy` retrieves `data_privacy.md`, but one Final case still mixes product/food/service sources.
- `executive_misconduct` retrieves the dedicated KB and has no measured context pollution in Final.
- `food_safety` regressed on one Final case, where general crisis/service/executive sources outranked food/legal sources.
- No-hit accuracy did not hold: one unrelated invoice query retrieved `service_outage.md`.
