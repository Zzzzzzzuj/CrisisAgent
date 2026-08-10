# CrisisAgent Embedding Ablation - Hash vs BGE

## Experiment

- Python executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- sentence-transformers: `5.7.0`
- HF_HOME: `C:\Users\19726\Documents\hf-cache`
- split: `development`
- BGE model: `BAAI/bge-small-zh`
- BGE fallback to Hash: `False`
- Final Set run: `False`
- top_k: `5`
- min_rerank_score: `0.1`
- Fixed variables: Knowledge Base V2, cases, query rewrite, chunking, KeywordRetriever, VectorStore, HybridRetriever weights, RuleBasedReranker, threshold.
- This is a single-variable ablation: only the embedding model changes between Hash and BGE.
- Old Final Set was not run in this experiment.

## Conclusion

BGE should not directly replace Hash as the production default yet. On the Development Set, BGE improves Recall@3 from `0.4667` to `0.7` and lowers Context Pollution Rate from `0.1714` to `0.1481`, but No-hit Accuracy drops from `1.0` to `0.0`. BGE also adds clear latency and initialization cost. The current recommendation is to keep BGE as an optional quality mode and run a follow-up no-hit / threshold calibration experiment before considering a default switch.

## Overall Comparison

| Metric | Hash | BGE | Absolute Difference | Relative Difference |
|---|---:|---:|---:|---:|
| recall_at_1 | 0.3889 | 0.3889 | 0.0 | 0.0 |
| recall_at_3 | 0.4667 | 0.7 | 0.2333 | 0.4999 |
| recall_at_5 | 0.4889 | 0.7 | 0.2111 | 0.4318 |
| precision_at_1 | 0.8333 | 0.8333 | 0.0 | 0.0 |
| precision_at_3 | 0.3333 | 0.5 | 0.1667 | 0.5002 |
| precision_at_5 | 0.2111 | 0.3 | 0.0889 | 0.4211 |
| mrr | 1.0 | 1.0 | 0.0 | 0.0 |
| no_hit_accuracy | 1.0 | 0.0 | -1.0 | -1.0 |
| source_category_match | 0.6286 | 0.5 | -0.1286 | -0.2046 |
| context_pollution_rate | 0.1714 | 0.1481 | -0.0233 | -0.1359 |
| fallback_count | 0 | 0 | 0 | N/A |

## Performance

### hash

- model_initialization_ms: `0.0`
- query_embedding_latency_ms: `{'average': 0.03, 'p50': 0.03, 'p95': 0.05}`
- total_retrieval_latency_ms: `{'average': 5.04, 'p50': 2.13, 'p95': 12.1}`
- query_embedding_call_count: `63`

### bge

- model_initialization_ms: `15867.53`
- query_embedding_latency_ms: `{'average': 8.62, 'p50': 8.6, 'p95': 9.84}`
- total_retrieval_latency_ms: `{'average': 33.28, 'p50': 14.4, 'p95': 76.81}`
- query_embedding_call_count: `63`

## Category Comparison

### data_privacy

- recall_at_3: Hash `0.3333` | BGE `0.4444`
- mrr: Hash `1.0` | BGE `1.0`
- no_hit_accuracy: Hash `0.0` | BGE `0.0`
- source_category_match: Hash `0.6` | BGE `0.6667`
- context_pollution_rate: Hash `0.2` | BGE `0.0`

### executive_misconduct

- recall_at_3: Hash `0.6111` | BGE `0.7778`
- mrr: Hash `1.0` | BGE `1.0`
- no_hit_accuracy: Hash `0.0` | BGE `0.0`
- source_category_match: Hash `0.625` | BGE `0.75`
- context_pollution_rate: Hash `0.25` | BGE `0.125`

### food_safety

- recall_at_3: Hash `0.6111` | BGE `0.7222`
- mrr: Hash `1.0` | BGE `1.0`
- no_hit_accuracy: Hash `0.0` | BGE `0.0`
- source_category_match: Hash `1.0` | BGE `0.625`
- context_pollution_rate: Hash `0.0` | BGE `0.0`

### product_quality

- recall_at_3: Hash `0.3333` | BGE `0.6667`
- mrr: Hash `1.0` | BGE `1.0`
- no_hit_accuracy: Hash `0.0` | BGE `0.0`
- source_category_match: Hash `0.5714` | BGE `0.6667`
- context_pollution_rate: Hash `0.2857` | BGE `0.1111`

### service_outage

- recall_at_3: Hash `0.4444` | BGE `0.8889`
- mrr: Hash `1.0` | BGE `1.0`
- no_hit_accuracy: Hash `0.0` | BGE `0.0`
- source_category_match: Hash `0.375` | BGE `0.6`
- context_pollution_rate: Hash `0.125` | BGE `0.0`

### unrelated

- recall_at_3: Hash `0.0` | BGE `0.0`
- mrr: Hash `0.0` | BGE `0.0`
- no_hit_accuracy: Hash `1.0` | BGE `0.0`
- source_category_match: Hash `1.0` | BGE `0.0`
- context_pollution_rate: Hash `0.0` | BGE `0.4615`

## Biggest Improvements

### rag_product_quality_dev_001

- category: `product_quality`
- query: `新机电池鼓包 产品质量 投诉 售后检测`
- delta: `0.8334`
- reason: `cross_domain_confusion_reduced`
- Hash vector top results: `[{'source': 'product_quality.md', 'score': 0.4167}, {'source': 'food_safety.md', 'score': 0.3161}, {'source': 'product_quality.md', 'score': 0.3091}, {'source': 'executive_misconduct.md', 'score': 0.2981}, {'source': 'food_safety.md', 'score': 0.2981}]`
- Hash final sources: `['product_quality.md', 'food_safety.md']`
- Hash rerank scores: `[0.1275, 0.1106, 0.109]`
- BGE vector top results: `[{'source': 'product_quality.md', 'score': 0.7783}, {'source': 'service_outage.md', 'score': 0.7658}, {'source': 'product_quality.md', 'score': 0.7609}, {'source': 'product_quality.md', 'score': 0.7476}, {'source': 'crisis_response.md', 'score': 0.7356}]`
- BGE final sources: `['product_quality.md', 'service_outage.md', 'crisis_response.md']`
- BGE rerank scores: `[0.2202, 0.2179, 0.2136, 0.1915, 0.1839]`

### rag_service_outage_dev_001

- category: `service_outage`
- query: `在线服务大面积无法登录 用户投诉客服无响应`
- delta: `0.75`
- reason: `cross_domain_confusion_reduced`
- Hash vector top results: `[{'source': 'service_outage.md', 'score': 0.4906}, {'source': 'data_privacy.md', 'score': 0.4508}, {'source': 'data_privacy.md', 'score': 0.4126}, {'source': 'product_quality.md', 'score': 0.3792}, {'source': 'food_safety.md', 'score': 0.3757}]`
- Hash final sources: `['service_outage.md', 'data_privacy.md', 'product_quality.md', 'food_safety.md']`
- Hash rerank scores: `[0.1851, 0.1202, 0.1182, 0.1098, 0.1014]`
- BGE vector top results: `[{'source': 'service_outage.md', 'score': 0.8501}, {'source': 'service_outage.md', 'score': 0.8086}, {'source': 'crisis_response.md', 'score': 0.771}, {'source': 'product_quality.md', 'score': 0.7627}, {'source': 'data_privacy.md', 'score': 0.7619}]`
- BGE final sources: `['service_outage.md', 'crisis_response.md', 'product_quality.md', 'data_privacy.md']`
- BGE rerank scores: `[0.275, 0.2197, 0.1928, 0.1907, 0.1905]`

### rag_data_privacy_dev_003

- category: `data_privacy`
- query: `APP 过度收集通讯录权限 用户担心资料被滥用`
- delta: `0.6667`
- reason: `cross_domain_confusion_reduced`
- Hash vector top results: `[{'source': 'food_safety.md', 'score': 0.5022}, {'source': 'data_privacy.md', 'score': 0.483}, {'source': 'service_outage.md', 'score': 0.4797}, {'source': 'data_privacy.md', 'score': 0.4518}, {'source': 'data_privacy.md', 'score': 0.4116}]`
- Hash final sources: `['data_privacy.md', 'service_outage.md', 'food_safety.md']`
- Hash rerank scores: `[0.1286, 0.1278, 0.1255, 0.1208, 0.1187]`
- BGE vector top results: `[{'source': 'data_privacy.md', 'score': 0.8413}, {'source': 'crisis_response.md', 'score': 0.8072}, {'source': 'service_outage.md', 'score': 0.7891}, {'source': 'product_quality.md', 'score': 0.7884}, {'source': 'data_privacy.md', 'score': 0.7771}]`
- BGE final sources: `['data_privacy.md', 'crisis_response.md', 'service_outage.md', 'product_quality.md']`
- BGE rerank scores: `[0.2104, 0.2022, 0.2018, 0.1973, 0.1971]`

### rag_executive_misconduct_dev_002

- category: `executive_misconduct`
- query: `负责人直播嘲讽消费者 舆论抵制 管理层道歉`
- delta: `0.6667`
- reason: `cross_domain_confusion_reduced`
- Hash vector top results: `[{'source': 'executive_misconduct.md', 'score': 0.3866}, {'source': 'food_safety.md', 'score': 0.3762}, {'source': 'executive_misconduct.md', 'score': 0.345}, {'source': 'executive_misconduct.md', 'score': 0.332}, {'source': 'executive_misconduct.md', 'score': 0.294}]`
- Hash final sources: `['executive_misconduct.md', 'food_safety.md']`
- Hash rerank scores: `[0.1146, 0.1124, 0.1098]`
- BGE vector top results: `[{'source': 'executive_misconduct.md', 'score': 0.7905}, {'source': 'executive_misconduct.md', 'score': 0.7796}, {'source': 'executive_misconduct.md', 'score': 0.7657}, {'source': 'crisis_response.md', 'score': 0.7636}, {'source': 'food_safety.md', 'score': 0.752}]`
- BGE final sources: `['executive_misconduct.md', 'food_safety.md', 'crisis_response.md']`
- BGE rerank scores: `[0.2292, 0.2107, 0.2038, 0.1915, 0.1909]`

### rag_service_outage_dev_002

- category: `service_outage`
- query: `系统宕机 服务恢复 故障排查 进展更新`
- delta: `0.5`
- reason: `semantic_match_improved`
- Hash vector top results: `[{'source': 'service_outage.md', 'score': 0.5}, {'source': 'service_outage.md', 'score': 0.4368}, {'source': 'service_outage.md', 'score': 0.3958}, {'source': 'data_privacy.md', 'score': 0.3707}, {'source': 'product_quality.md', 'score': 0.319}]`
- Hash final sources: `['service_outage.md', 'data_privacy.md']`
- Hash rerank scores: `[0.1717, 0.1687, 0.1615, 0.102]`
- BGE vector top results: `[{'source': 'service_outage.md', 'score': 0.8749}, {'source': 'crisis_response.md', 'score': 0.8222}, {'source': 'service_outage.md', 'score': 0.8057}, {'source': 'product_quality.md', 'score': 0.804}, {'source': 'service_outage.md', 'score': 0.7975}]`
- BGE final sources: `['service_outage.md', 'crisis_response.md', 'product_quality.md']`
- BGE rerank scores: `[0.2625, 0.2618, 0.2451, 0.2056, 0.201]`


## Biggest Regressions

### rag_unrelated_dev_001

- category: `unrelated`
- query: `会员积分多久到账 客服查询`
- delta: `-2.0`
- reason: `new_false_positive`
- Hash vector top results: `[{'source': 'product_quality.md', 'score': 0.3349}, {'source': 'service_outage.md', 'score': 0.3203}, {'source': 'executive_misconduct.md', 'score': 0.3172}, {'source': 'data_privacy.md', 'score': 0.3158}, {'source': 'product_quality.md', 'score': 0.2819}]`
- Hash final sources: `[]`
- Hash rerank scores: `[]`
- BGE vector top results: `[{'source': 'service_outage.md', 'score': 0.7418}, {'source': 'legal_risk_rules.md', 'score': 0.7326}, {'source': 'service_outage.md', 'score': 0.7313}, {'source': 'service_outage.md', 'score': 0.7277}, {'source': 'data_privacy.md', 'score': 0.726}]`
- BGE final sources: `['service_outage.md', 'legal_risk_rules.md', 'data_privacy.md']`
- BGE rerank scores: `[0.1855, 0.1832, 0.1828, 0.182, 0.1815]`

### rag_unrelated_dev_002

- category: `unrelated`
- query: `门店春节营业时间 安排 查询`
- delta: `-2.0`
- reason: `new_false_positive`
- Hash vector top results: `[{'source': 'product_quality.md', 'score': 0.3504}, {'source': 'data_privacy.md', 'score': 0.3369}, {'source': 'product_quality.md', 'score': 0.3054}, {'source': 'data_privacy.md', 'score': 0.2932}, {'source': 'service_outage.md', 'score': 0.2807}]`
- Hash final sources: `[]`
- Hash rerank scores: `[]`
- BGE vector top results: `[{'source': 'crisis_response.md', 'score': 0.7776}, {'source': 'service_outage.md', 'score': 0.7758}, {'source': 'legal_risk_rules.md', 'score': 0.7694}, {'source': 'product_quality.md', 'score': 0.7668}, {'source': 'food_safety.md', 'score': 0.7628}]`
- BGE final sources: `['crisis_response.md', 'service_outage.md', 'legal_risk_rules.md', 'product_quality.md', 'food_safety.md']`
- BGE rerank scores: `[0.1944, 0.194, 0.1923, 0.1917, 0.1907]`

### rag_unrelated_dev_003

- category: `unrelated`
- query: `APP 首页深色模式入口 产品建议`
- delta: `-2.0`
- reason: `new_false_positive`
- Hash vector top results: `[{'source': 'product_quality.md', 'score': 0.3611}, {'source': 'service_outage.md', 'score': 0.3154}, {'source': 'food_safety.md', 'score': 0.2964}, {'source': 'service_outage.md', 'score': 0.2942}, {'source': 'data_privacy.md', 'score': 0.2832}]`
- Hash final sources: `[]`
- Hash rerank scores: `[]`
- BGE vector top results: `[{'source': 'data_privacy.md', 'score': 0.7855}, {'source': 'service_outage.md', 'score': 0.7822}, {'source': 'product_quality.md', 'score': 0.7771}, {'source': 'food_safety.md', 'score': 0.7614}, {'source': 'crisis_response.md', 'score': 0.7604}]`
- BGE final sources: `['data_privacy.md', 'service_outage.md', 'product_quality.md', 'food_safety.md', 'crisis_response.md']`
- BGE rerank scores: `[0.1963, 0.1956, 0.1943, 0.1903, 0.1901]`

### rag_food_safety_dev_001

- category: `food_safety`
- query: `过期原料 食品安全 监管介入`
- delta: `0.0`
- reason: `no_material_change`
- Hash vector top results: `[{'source': 'food_safety.md', 'score': 0.4984}, {'source': 'food_safety.md', 'score': 0.4613}, {'source': 'food_safety.md', 'score': 0.4226}, {'source': 'product_quality.md', 'score': 0.4005}, {'source': 'product_quality.md', 'score': 0.3697}]`
- Hash final sources: `['food_safety.md']`
- Hash rerank scores: `[0.475, 0.4158, 0.3988, 0.3778, 0.3667]`
- BGE vector top results: `[{'source': 'food_safety.md', 'score': 0.8578}, {'source': 'food_safety.md', 'score': 0.8549}, {'source': 'food_safety.md', 'score': 0.8304}, {'source': 'product_quality.md', 'score': 0.8208}, {'source': 'crisis_response.md', 'score': 0.7871}]`
- BGE final sources: `['food_safety.md', 'product_quality.md']`
- BGE rerank scores: `[0.502, 0.4701, 0.4687, 0.4425, 0.2463]`

### rag_food_safety_dev_002

- category: `food_safety`
- query: `餐饮后厨卫生混乱 视频曝光 消费者担忧`
- delta: `0.0`
- reason: `no_material_change`
- Hash vector top results: `[{'source': 'legal_risk_rules.md', 'score': 0.3931}, {'source': 'product_quality.md', 'score': 0.3828}, {'source': 'crisis_response.md', 'score': 0.3559}, {'source': 'food_safety.md', 'score': 0.3485}, {'source': 'product_quality.md', 'score': 0.3155}]`
- Hash final sources: `['crisis_response.md', 'food_safety.md']`
- Hash rerank scores: `[0.2041, 0.1875, 0.1875, 0.1613, 0.1603]`
- BGE vector top results: `[{'source': 'food_safety.md', 'score': 0.8095}, {'source': 'food_safety.md', 'score': 0.7813}, {'source': 'service_outage.md', 'score': 0.7776}, {'source': 'product_quality.md', 'score': 0.7739}, {'source': 'food_safety.md', 'score': 0.7732}]`
- BGE final sources: `['food_safety.md', 'crisis_response.md', 'legal_risk_rules.md', 'product_quality.md']`
- BGE rerank scores: `[0.2403, 0.2363, 0.2311, 0.2202, 0.2172]`
