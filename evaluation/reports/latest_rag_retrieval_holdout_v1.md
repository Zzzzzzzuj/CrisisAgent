# Reranker v2 Retrieval Holdout v1 First Frozen Validation

## Metadata

- experiment: `Reranker v2 Retrieval Holdout v1 First Frozen Validation`
- dataset: `evaluation\rag_retrieval_holdout_v1.json`
- protocol: `evaluation\reports\rag_retrieval_holdout_v1_protocol.md`
- reranker_v2_frozen_commit: `22fed48`
- holdout_frozen_commit: `33cf7bf`
- protocol_frozen_commit: `33cf7bf`
- evaluation_commit: `33cf7bf`
- python_executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- sentence_transformers_version: `5.7.0`
- bge_model: `BAAI/bge-small-zh`
- bge_fallback_used: `False`
- fallback_count: `0`
- candidate_pool_parity: `True`

## Metric Scope

- evaluation_scope: `positive_only`
- total_cases: `30`
- gate_applied: `False`
- dedupe_level: `source`
- top_k: `5`
- min_rerank_score: `0.1`
- only_variable: `reranker`

## Dataset Composition

- {'data_privacy': 6, 'executive_misconduct': 6, 'food_safety': 6, 'product_quality': 6, 'service_outage': 6}

## Fixed Variables

- `Knowledge Base V2`
- `Query Rewrite`
- `KeywordRetriever`
- `BGE VectorRetriever with BAAI/bge-small-zh`
- `HybridRetriever 0.5/0.5`
- `single shared candidate pool per case`
- `Top-K=5`
- `min_rerank_score=0.1`
- `source-level dedupe`

## Formulas

- Old Reranker: `0.5 * retrieval_score + 0.2 * title_match + 0.15 * source_match + 0.15 * keyword_overlap`
- Reranker v2: `0.48 * retrieval_score + 0.17 * title_match + 0.10 * source_match + 0.14 * keyword_overlap + domain_adjustment`

## Metric Comparison

| Metric | Old | Reranker v2 | Difference |
|---|---:|---:|---:|
| recall_at_1 | `0.6667` | `0.7` | `0.0333` |
| recall_at_3 | `0.9` | `0.9` | `0.0` |
| recall_at_5 | `0.9` | `0.9` | `0.0` |
| precision_at_1 | `0.6667` | `0.7` | `0.0333` |
| precision_at_3 | `0.3` | `0.3` | `0.0` |
| precision_at_5 | `0.18` | `0.18` | `0.0` |
| mrr | `0.7778` | `0.7944` | `0.0166` |
| source_category_match | `0.4611` | `0.6278` | `0.1667` |
| context_pollution_rate | `0.4722` | `0.3222` | `-0.15` |
| acceptable_top1_count | `20` | `21` | `1` |
| acceptable_top3_count | `27` | `27` | `0` |
| pollution_case_count | `25` | `16` | `-9` |
| pollution_relative_reduction | `-` | `0.3177` | `-` |

## Per-Domain Metrics

| Category | Old Recall@3 | v2 Recall@3 | Old MRR | v2 MRR | Old SCM | v2 SCM | Old Pollution | v2 Pollution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| data_privacy | `0.8333` | `0.8333` | `0.5833` | `0.6667` | `0.5833` | `0.6667` | `0.3611` | `0.3055` |
| executive_misconduct | `0.8333` | `0.8333` | `0.6667` | `0.6667` | `0.5555` | `0.5555` | `0.25` | `0.25` |
| food_safety | `1.0` | `1.0` | `0.8055` | `0.8055` | `0.3889` | `0.6111` | `0.5833` | `0.3611` |
| product_quality | `0.8333` | `0.8333` | `0.8333` | `0.8333` | `0.3333` | `0.5278` | `0.6111` | `0.4722` |
| service_outage | `1.0` | `1.0` | `1.0` | `1.0` | `0.4444` | `0.7778` | `0.5556` | `0.2222` |

## Cross-Domain Confusion

- Old: `{'service_outage->product_quality.md': 5, 'food_safety->product_quality.md': 4, 'data_privacy->service_outage.md': 4, 'product_quality->data_privacy.md': 4, 'food_safety->service_outage.md': 3, 'product_quality->food_safety.md': 3, 'food_safety->executive_misconduct.md': 2, 'service_outage->data_privacy.md': 2, 'product_quality->executive_misconduct.md': 2, 'food_safety->data_privacy.md': 1, 'data_privacy->executive_misconduct.md': 1, 'data_privacy->food_safety.md': 1, 'service_outage->food_safety.md': 1, 'product_quality->service_outage.md': 1, 'executive_misconduct->data_privacy.md': 1, 'executive_misconduct->service_outage.md': 1, 'executive_misconduct->food_safety.md': 1, 'executive_misconduct->product_quality.md': 1}`
- Reranker v2: `{'food_safety->service_outage.md': 3, 'data_privacy->service_outage.md': 3, 'product_quality->data_privacy.md': 3, 'food_safety->product_quality.md': 2, 'service_outage->data_privacy.md': 2, 'service_outage->product_quality.md': 2, 'product_quality->food_safety.md': 2, 'food_safety->data_privacy.md': 1, 'data_privacy->executive_misconduct.md': 1, 'data_privacy->food_safety.md': 1, 'product_quality->service_outage.md': 1, 'executive_misconduct->data_privacy.md': 1, 'executive_misconduct->service_outage.md': 1, 'executive_misconduct->food_safety.md': 1, 'executive_misconduct->product_quality.md': 1}`

## Wrong-Category Rank Distribution

- Old: `{'rank1': 4, 'rank2': 21, 'rank3': 13, 'rank4': 0, 'rank5': 0}`
- Reranker v2: `{'rank1': 5, 'rank2': 12, 'rank3': 8, 'rank4': 0, 'rank5': 0}`

## Regression and Improvement Cases

- new_top3_regression_count: `1`
- top3_retrieval_regressions: `[{'case_id': 'retrieval_holdout_v1_product_quality_004', 'category': 'product_quality', 'event': '某批次婴儿推车在使用中出现刹车失灵反馈，门店要求总部给出检查流程、维修指引和家长沟通话术。', 'acceptable_sources': ['product_quality.md'], 'old_top3': ['product_quality.md', 'executive_misconduct.md', 'food_safety.md'], 'v2_top3': ['food_safety.md']}]`
- improvement_cases: `[{'case_id': 'retrieval_holdout_v1_product_quality_001', 'category': 'product_quality', 'event': '同型号智能水杯被多名用户反馈底座发热和轻微变形，电商评论区开始集中质疑安全性，品牌需要安排检测和售后方案。', 'acceptable_sources': ['product_quality.md'], 'old_top3': ['crisis_response.md', 'data_privacy.md', 'food_safety.md'], 'v2_top3': ['product_quality.md']}]`
- pollution_improvement_cases: `[{'case_id': 'retrieval_holdout_v1_food_safety_001', 'category': 'food_safety', 'event': '连锁甜品店的新款奶油蛋糕在周末售出后，多名顾客反馈腹痛和呕吐，门店正在整理批次记录、冷链温度和对外回应口径。', 'acceptable_sources': ['food_safety.md'], 'old_top3': ['food_safety.md', 'product_quality.md', 'executive_misconduct.md'], 'v2_top3': ['food_safety.md'], 'old_forbidden_sources': ['executive_misconduct.md', 'product_quality.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_food_safety_003', 'category': 'food_safety', 'event': '某饮料门店员工发现同批次杯装果茶出现沉淀和刺鼻气味，短视频评论区已有消费者询问是否还能饮用。', 'acceptable_sources': ['food_safety.md'], 'old_top3': ['food_safety.md', 'executive_misconduct.md', 'product_quality.md'], 'v2_top3': ['food_safety.md'], 'old_forbidden_sources': ['executive_misconduct.md', 'product_quality.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_data_privacy_001', 'category': 'data_privacy', 'event': '部分用户登录会员中心后看到了其他账号的收货地址和手机号截图，相关图片已经在社群传播，平台需要说明排查和保护措施。', 'acceptable_sources': ['data_privacy.md'], 'old_top3': ['crisis_response.md', 'data_privacy.md', 'service_outage.md'], 'v2_top3': ['data_privacy.md'], 'old_forbidden_sources': ['service_outage.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_service_outage_001', 'category': 'service_outage', 'event': '晚高峰期间支付页面长时间转圈，部分订单重复扣款，商户无法完成收款，平台需要发布服务恢复和补偿说明。', 'acceptable_sources': ['service_outage.md'], 'old_top3': ['service_outage.md', 'product_quality.md'], 'v2_top3': ['service_outage.md'], 'old_forbidden_sources': ['product_quality.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_service_outage_003', 'category': 'service_outage', 'event': '订票系统在活动开售后频繁报错，用户排队资格被重置，社交平台要求公司解释技术排查和后续处理。', 'acceptable_sources': ['service_outage.md'], 'old_top3': ['service_outage.md', 'product_quality.md'], 'v2_top3': ['service_outage.md'], 'old_forbidden_sources': ['product_quality.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_service_outage_004', 'category': 'service_outage', 'event': '外卖平台部分区域骑手端无法接单，用户端仍显示预计送达时间，商家投诉订单堆积，需要对外说明故障处置。', 'acceptable_sources': ['service_outage.md'], 'old_top3': ['service_outage.md', 'food_safety.md'], 'v2_top3': ['service_outage.md'], 'old_forbidden_sources': ['food_safety.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_service_outage_005', 'category': 'service_outage', 'event': '多地门店的会员结算系统同一时间离线，收银员只能手写登记，顾客排队抱怨，技术团队正在确认恢复时间。', 'acceptable_sources': ['service_outage.md'], 'old_top3': ['service_outage.md', 'product_quality.md'], 'v2_top3': ['service_outage.md'], 'old_forbidden_sources': ['product_quality.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_product_quality_001', 'category': 'product_quality', 'event': '同型号智能水杯被多名用户反馈底座发热和轻微变形，电商评论区开始集中质疑安全性，品牌需要安排检测和售后方案。', 'acceptable_sources': ['product_quality.md'], 'old_top3': ['crisis_response.md', 'data_privacy.md', 'food_safety.md'], 'v2_top3': ['product_quality.md'], 'old_forbidden_sources': ['data_privacy.md', 'food_safety.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_product_quality_002', 'category': 'product_quality', 'event': '儿童学习灯使用几周后陆续出现外壳开裂，家长群要求品牌说明批次、材质和退换安排。', 'acceptable_sources': ['product_quality.md'], 'old_top3': ['product_quality.md', 'executive_misconduct.md'], 'v2_top3': ['product_quality.md'], 'old_forbidden_sources': ['executive_misconduct.md'], 'v2_forbidden_sources': []}, {'case_id': 'retrieval_holdout_v1_product_quality_004', 'category': 'product_quality', 'event': '某批次婴儿推车在使用中出现刹车失灵反馈，门店要求总部给出检查流程、维修指引和家长沟通话术。', 'acceptable_sources': ['product_quality.md'], 'old_top3': ['product_quality.md', 'executive_misconduct.md', 'food_safety.md'], 'v2_top3': ['food_safety.md'], 'old_forbidden_sources': ['executive_misconduct.md', 'food_safety.md'], 'v2_forbidden_sources': ['food_safety.md']}]`
- newly_introduced_pollution: `[]`

## Primary Criteria

- `v2_recall_at_3_min`: `PASS`
- `recall_at_3_drop_within_0_05`: `PASS`
- `context_pollution_lower_than_old`: `PASS`
- `pollution_relative_reduction_at_least_20_percent`: `PASS`
- `source_category_match_higher_than_old`: `PASS`
- `new_top3_regression_cases_lte_2`: `PASS`
- `each_domain_recall_at_3_at_least_0_75`: `PASS`
- Overall Result: `PASS`

## Historical Development Context

- Phase 4B Development was Challenge v3 post-hoc development only.
- Development Recall@3: `0.95 -> 0.95`
- Development Context Pollution: `0.4314 -> 0.1765`
- Development Source Category Match: `0.3921 -> 0.5882`
- These development numbers are not mixed with Retrieval Holdout v1 before/after metrics.

## Limitations

- Retrieval Holdout v1 is no longer untouched after this first formal run.
- This report isolates Reranker behavior and does not apply Retrieval Need Gate.
- Any future Reranker change requires a new frozen retrieval holdout.
