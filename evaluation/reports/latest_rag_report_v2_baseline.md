# CrisisAgent RAG Evaluation V2 Baseline

## Baseline Configuration

- Retriever: `current_default_pipeline`
- Hybrid retrieval: `True`
- Embedding: `HashEmbeddingModel`
- Reranker: `RuleBasedReranker`
- min_rerank_score: `0.1`
- top_k: `5`

## Overall Metrics

- Total cases: `30`
- Hit case count: `25`
- No-hit case count: `5`
- Recall@1: `0.1933`
- Recall@3: `0.2933`
- Recall@5: `0.2933`
- Precision@1: `0.3`
- Precision@3: `0.1555`
- Precision@5: `0.0933`
- MRR: `0.42`
- No-hit Accuracy: `1.0`
- Source Category Match: `0.6667`
- Context Pollution Rate: `0.3077`
- Fallback count: `0`

## Split Metrics

### development

- Total cases: `18`
- Hit case count: `15`
- No-hit case count: `3`
- Recall@1: `0.1889`
- Recall@3: `0.2889`
- Recall@5: `0.2889`
- Precision@1: `0.3333`
- Precision@3: `0.1667`
- Precision@5: `0.1`
- MRR: `0.4667`
- No-hit Accuracy: `1.0`
- Source Category Match: `0.625`
- Context Pollution Rate: `0.375`
- Fallback count: `0`

### final

- Total cases: `12`
- Hit case count: `10`
- No-hit case count: `2`
- Recall@1: `0.2`
- Recall@3: `0.3`
- Recall@5: `0.3`
- Precision@1: `0.25`
- Precision@3: `0.1389`
- Precision@5: `0.0833`
- MRR: `0.35`
- No-hit Accuracy: `1.0`
- Source Category Match: `0.7333`
- Context Pollution Rate: `0.2`
- Fallback count: `0`

## Category Metrics

### data_privacy

- Total cases: `5`
- Hit case count: `5`
- No-hit case count: `0`
- Recall@1: `0.2`
- Recall@3: `0.4`
- Recall@5: `0.4`
- Precision@1: `0.4`
- Precision@3: `0.2667`
- Precision@5: `0.16`
- MRR: `0.5`
- No-hit Accuracy: `0.0`
- Source Category Match: `0.5`
- Context Pollution Rate: `0.5`
- Fallback count: `0`

### executive_misconduct

- Total cases: `5`
- Hit case count: `5`
- No-hit case count: `0`
- Recall@1: `0.4`
- Recall@3: `0.4`
- Recall@5: `0.4`
- Precision@1: `0.6`
- Precision@3: `0.2`
- Precision@5: `0.12`
- MRR: `0.6`
- No-hit Accuracy: `0.0`
- Source Category Match: `0.5`
- Context Pollution Rate: `0.5`
- Fallback count: `0`

### food_safety

- Total cases: `5`
- Hit case count: `5`
- No-hit case count: `0`
- Recall@1: `0.3667`
- Recall@3: `0.5667`
- Recall@5: `0.5667`
- Precision@1: `0.8`
- Precision@3: `0.4`
- Precision@5: `0.24`
- MRR: `0.9`
- No-hit Accuracy: `0.0`
- Source Category Match: `0.8571`
- Context Pollution Rate: `0.0`
- Fallback count: `0`

### product_quality

- Total cases: `5`
- Hit case count: `5`
- No-hit case count: `0`
- Recall@1: `0.0`
- Recall@3: `0.1`
- Recall@5: `0.1`
- Precision@1: `0.0`
- Precision@3: `0.0667`
- Precision@5: `0.04`
- MRR: `0.1`
- No-hit Accuracy: `0.0`
- Source Category Match: `0.5`
- Context Pollution Rate: `0.5`
- Fallback count: `0`

### service_outage

- Total cases: `5`
- Hit case count: `5`
- No-hit case count: `0`
- Recall@1: `0.0`
- Recall@3: `0.0`
- Recall@5: `0.0`
- Precision@1: `0.0`
- Precision@3: `0.0`
- Precision@5: `0.0`
- MRR: `0.0`
- No-hit Accuracy: `0.0`
- Source Category Match: `0.8`
- Context Pollution Rate: `0.2`
- Fallback count: `0`

### unrelated

- Total cases: `5`
- Hit case count: `0`
- No-hit case count: `5`
- Recall@1: `0.0`
- Recall@3: `0.0`
- Recall@5: `0.0`
- Precision@1: `0.0`
- Precision@3: `0.0`
- Precision@5: `0.0`
- MRR: `0.0`
- No-hit Accuracy: `1.0`
- Source Category Match: `1.0`
- Context Pollution Rate: `0.0`
- Fallback count: `0`

## Worst Cases

### rag_data_privacy_dev_003

- Category: `data_privacy`
- Query: APP 过度收集通讯录权限 用户担心资料被滥用
- Acceptable sources: `legal_risk_rules.md, crisis_response.md`
- Actual sources: `food_safety.md`
- Scores: `[0.2511]`
- Rerank scores: `[0.1255]`
- Retrieval type: `hybrid`
- Fallback used: `False`
- Failure reason: `wrong_category`

### rag_data_privacy_final_002

- Category: `data_privacy`
- Query: 订单地址 电话 被陌生人获取 信息安全 排查
- Acceptable sources: `legal_risk_rules.md, crisis_response.md`
- Actual sources: `food_safety.md`
- Scores: `[0.1693, 0.184]`
- Rerank scores: `[0.1159, 0.1045]`
- Retrieval type: `hybrid`
- Fallback used: `False`
- Failure reason: `wrong_category`

### rag_service_outage_dev_001

- Category: `service_outage`
- Query: 在线服务大面积无法登录 用户投诉客服无响应
- Acceptable sources: `crisis_response.md`
- Actual sources: `food_safety.md`
- Scores: `[0.1878]`
- Rerank scores: `[0.1014]`
- Retrieval type: `hybrid`
- Fallback used: `False`
- Failure reason: `wrong_category`

### rag_product_quality_dev_001

- Category: `product_quality`
- Query: 新机电池鼓包 产品质量 投诉 售后检测
- Acceptable sources: `legal_risk_rules.md, crisis_response.md`
- Actual sources: `food_safety.md`
- Scores: `[0.158]`
- Rerank scores: `[0.109]`
- Retrieval type: `hybrid`
- Fallback used: `False`
- Failure reason: `wrong_category`

### rag_product_quality_final_001

- Category: `product_quality`
- Query: 运动器材刹车部件松动 消费者担心使用安全
- Acceptable sources: `legal_risk_rules.md, crisis_response.md`
- Actual sources: `food_safety.md`
- Scores: `[0.1898]`
- Rerank scores: `[0.137]`
- Retrieval type: `hybrid`
- Fallback used: `False`
- Failure reason: `wrong_category`
