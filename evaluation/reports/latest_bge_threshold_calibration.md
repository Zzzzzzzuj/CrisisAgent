# CrisisAgent BGE Threshold Calibration

## Experiment

- Python executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- sentence-transformers: `5.7.0`
- HF_HOME: `C:\Users\19726\Documents\hf-cache`
- BGE model: `BAAI/bge-small-zh`
- split: `development`
- old Final Set run: `False`
- production min_rerank_score unchanged: `0.1`
- negative calibration cases: `24`
- negative type counts: `{'business_non_crisis': 8, 'hard_negative': 8, 'unrelated': 8}`

## Score Distribution

- Positive top1 rerank score: `{'min': 0.1855, 'p10': 0.1957, 'p25': 0.2217, 'median': 0.2414, 'p75': 0.2719, 'p90': 0.3729, 'p95': 0.4107, 'max': 0.502}`
- Negative overall top1 rerank score: `{'min': 0.1744, 'p10': 0.1787, 'p25': 0.1889, 'median': 0.1946, 'p75': 0.2169, 'p90': 0.2442, 'p95': 0.2495, 'max': 0.3584}`
- business_non_crisis top1 rerank score: `{'min': 0.1863, 'p10': 0.1888, 'p25': 0.1912, 'median': 0.1942, 'p75': 0.1964, 'p90': 0.2051, 'p95': 0.2101, 'max': 0.2151}`
- hard_negative top1 rerank score: `{'min': 0.2041, 'p10': 0.2079, 'p25': 0.2115, 'median': 0.2366, 'p75': 0.2474, 'p90': 0.2825, 'p95': 0.3205, 'max': 0.3584}`
- unrelated top1 rerank score: `{'min': 0.1744, 'p10': 0.1764, 'p25': 0.1783, 'median': 0.1818, 'p75': 0.1908, 'p90': 0.201, 'p95': 0.2116, 'max': 0.2223}`

## Threshold Sweep

| threshold | Recall@3 | MRR | No-hit overall | unrelated | business | hard_negative | Pollution | FP Count | Recall Loss | FP Reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | 0.7 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1481 | 24 | 0.0 | 0 |
| 0.12 | 0.7 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1481 | 24 | 0.0 | 0 |
| 0.15 | 0.7 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1481 | 24 | 0.0 | 0 |
| 0.18 | 0.7 | 1.0 | 0.1667 | 0.5 | 0.0 | 0.0 | 0.1481 | 20 | 0.0 | 4 |
| 0.2 | 0.5444 | 1.0 | 0.5417 | 0.875 | 0.75 | 0.0 | 0.0645 | 11 | 0.1556 | 13 |
| 0.22 | 0.4667 | 0.9333 | 0.75 | 0.875 | 1.0 | 0.375 | 0.04 | 6 | 0.2333 | 18 |
| 0.25 | 0.2111 | 0.4667 | 0.9167 | 1.0 | 1.0 | 0.75 | 0.0 | 2 | 0.4889 | 22 |
| 0.28 | 0.1 | 0.2667 | 0.9583 | 1.0 | 1.0 | 0.875 | 0.0 | 1 | 0.6 | 23 |
| 0.3 | 0.0778 | 0.2 | 0.9583 | 1.0 | 1.0 | 0.875 | 0.0 | 1 | 0.6222 | 23 |

## Recommendation

- recommended_threshold: `None`
- backup_threshold: `None`
- trade_off: No clear Pareto point found. BGE needs an additional no-hit gate or retrieval confidence gate.
- needs_no_hit_gate: `True`
- conclusion: Positive and negative top1 rerank score distributions overlap clearly. A single min_rerank_score threshold cannot keep both high Recall and high No-hit accuracy in this experiment.
- next_step: Do not treat 0.20 or 0.22 as a final recommended threshold. The next experiment should add an independent retrieval-need / no-hit gate.

## Hardest Hard Negatives

### neg_hard_negative_006

- query: `监管政策讨论和行业合规趋势分析`
- top1_rerank_score: `0.3584`
- top3_rerank_scores: `[0.3584, 0.25, 0.25]`
- vector_top_sources: `['legal_risk_rules.md', 'crisis_response.md', 'executive_misconduct.md', 'data_privacy.md', 'food_safety.md']`
- vector_scores: `[0.7977, 0.7972, 0.7971, 0.7876, 0.7735]`
- final_sources: `['food_safety.md', 'legal_risk_rules.md', 'legal_risk_rules.md', 'legal_risk_rules.md', 'legal_risk_rules.md']`
- final_categories: `['food_safety', 'legal_risk_rules', 'legal_risk_rules', 'legal_risk_rules', 'legal_risk_rules']`

### neg_hard_negative_003

- query: `网友讨论三年前的历史投诉案例`
- top1_rerank_score: `0.25`
- top3_rerank_scores: `[0.25, 0.2203, 0.2175]`
- vector_top_sources: `['service_outage.md', 'crisis_response.md', 'product_quality.md', 'executive_misconduct.md', 'legal_risk_rules.md']`
- vector_scores: `[0.7959, 0.7902, 0.7875, 0.7871, 0.7794]`
- final_sources: `['crisis_response.md', 'crisis_response.md', 'crisis_response.md', 'food_safety.md', 'data_privacy.md']`
- final_categories: `['general_crisis_response', 'general_crisis_response', 'general_crisis_response', 'food_safety', 'data_privacy']`

### neg_hard_negative_001

- query: `用户想查询隐私政策入口在哪里`
- top1_rerank_score: `0.2465`
- top3_rerank_scores: `[0.2465, 0.2396, 0.2331]`
- vector_top_sources: `['data_privacy.md', 'crisis_response.md', 'data_privacy.md', 'service_outage.md', 'data_privacy.md']`
- vector_scores: `[0.8502, 0.7739, 0.7617, 0.7584, 0.7506]`
- final_sources: `['data_privacy.md', 'data_privacy.md', 'data_privacy.md', 'crisis_response.md', 'data_privacy.md']`
- final_categories: `['data_privacy', 'data_privacy', 'data_privacy', 'general_crisis_response', 'data_privacy']`

### neg_hard_negative_007

- query: `高管普通公开演讲的发言稿润色`
- top1_rerank_score: `0.239`
- top3_rerank_scores: `[0.239, 0.2045, 0.1935]`
- vector_top_sources: `['executive_misconduct.md', 'crisis_response.md', 'data_privacy.md', 'executive_misconduct.md', 'product_quality.md']`
- vector_scores: `[0.8562, 0.7743, 0.7655, 0.7607, 0.7567]`
- final_sources: `['executive_misconduct.md', 'executive_misconduct.md', 'crisis_response.md', 'data_privacy.md', 'product_quality.md']`
- final_categories: `['executive_misconduct', 'executive_misconduct', 'general_crisis_response', 'data_privacy', 'product_quality']`

### neg_hard_negative_002

- query: `消费者咨询产品保修期限和维修网点`
- top1_rerank_score: `0.2342`
- top3_rerank_scores: `[0.2342, 0.2079, 0.2056]`
- vector_top_sources: `['product_quality.md', 'service_outage.md', 'product_quality.md', 'product_quality.md', 'product_quality.md']`
- vector_scores: `[0.8242, 0.8223, 0.8126, 0.798, 0.7941]`
- final_sources: `['product_quality.md', 'product_quality.md', 'service_outage.md', 'product_quality.md', 'product_quality.md']`
- final_categories: `['product_quality', 'product_quality', 'service_outage', 'product_quality', 'product_quality']`
