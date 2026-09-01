# RAG Retrieval Evaluation Report

This is a lightweight offline Legal RAG retrieval benchmark. It does not call a real LLM.

## Summary

- total_cases: 8
- top1_source_hit_rate: 0.25
- top3_source_hit_rate: 0.25
- keyword_hit_rate: 0.125
- fallback_rate: 0.0
- average_score: 0.3119
- average_rerank_score: 0.2135
- context_pollution_rate: 0.7143
- backend_distribution: {'markdown': 5, 'json_vector': 14}

## Cases

### rag_eval_food_safety_001

- difficulty: easy
- expected_source_category: food_safety
- actual_source_categories: ['food_safety', 'food_safety', 'food_safety']
- top1_source_hit: True
- top3_source_hit: True
- context_precision: 1.0
- context_pollution_rate: 0.0
- keyword_hits: ['食品', '批次', '核查', '监管']
- fallback_used: False
- failure_reason: none

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | food_safety.md | food_safety | 0.375 | 0.3481 | markdown | ## 监管介入 食品安全事件可能引发市场监管部门介入。企业应表达积极配合监管调查，并根据核查结果依法依规采取整改、召回、赔付或其他补救措施。 |
| 2 | food_safety.md | food_safety | 0.3227 | 0.3168 | json_vector | # 食品安全危机知识 |
| 3 | food_safety.md | food_safety | 0.2732 | 0.3086 | json_vector | ## 消费者权益 食品安全危机会直接影响消费者信任。回应中应明确理解消费者担忧，说明投诉受理、批次排查、产品检测和后续进展同步安排。 |

### rag_eval_data_privacy_001

- difficulty: medium
- expected_source_category: data_privacy
- actual_source_categories: ['crisis_response', 'crisis_response', 'crisis_response']
- top1_source_hit: False
- top3_source_hit: False
- context_precision: 0.0
- context_pollution_rate: 1.0
- keyword_hits: ['核查']
- fallback_used: False
- failure_reason: expected_source_category_not_in_top3

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | crisis_response.md | crisis_response | 0.5 | 0.3463 | markdown | ## 初次回应 初次回应应包括关注事件、理解公众担忧、启动核查、持续同步进展。语气应先共情，再说明行动，避免只做程序性表态。 |
| 2 | crisis_response.md | crisis_response | 0.3333 | 0.2663 | json_vector | # 危机回应规范 |
| 3 | crisis_response.md | crisis_response | 0.2995 | 0.2501 | json_vector | ## 初次回应 初次回应应包括关注事件、理解公众担忧、启动核查、持续同步进展。语气应先共情，再说明行动，避免只做程序性表态。 |

### rag_eval_service_outage_001

- difficulty: medium
- expected_source_category: service_outage
- actual_source_categories: ['service_outage', 'service_outage', 'service_outage']
- top1_source_hit: True
- top3_source_hit: True
- context_precision: 1.0
- context_pollution_rate: 0.0
- keyword_hits: ['服务', '恢复', '用户通知']
- fallback_used: False
- failure_reason: expected_keywords_missing

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | service_outage.md | service_outage | 0.2682 | 0.1985 | json_vector | ## 服务异常确认 当平台出现无法登录、交易失败、页面崩溃、访问失败或大面积卡顿时，企业应及时确认已关注服务异常，并说明正在排查。回应应优先关注用户和客户受到的影响。 |
| 2 | service_outage.md | service_outage | 0.2386 | 0.1879 | json_vector | ## 影响范围 企业应评估受影响的用户、客户、区域、服务模块、订单或交易范围。影响范围尚未查清时，应使用谨慎表达，并承诺持续同步核查进展。 |
| 3 | service_outage.md | service_outage | 0.2411 | 0.1781 | json_vector | ## 用户通知与后续复盘 企业应通过官方渠道向用户通知进展，恢复后说明补偿、延期、订单核对或客户支持安排。事后应进行复盘，完善监控、容量、应急预案和发布流程。 |

### rag_eval_false_advertising_001

- difficulty: hard
- expected_source_category: false_advertising
- actual_source_categories: ['crisis_response', 'service_outage', 'crisis_response']
- top1_source_hit: False
- top3_source_hit: False
- context_precision: 0.0
- context_pollution_rate: 1.0
- keyword_hits: []
- fallback_used: False
- failure_reason: expected_source_category_not_in_top3

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | crisis_response.md | crisis_response | 0.5 | 0.24 | markdown | ## 初次回应 初次回应应包括关注事件、理解公众担忧、启动核查、持续同步进展。语气应先共情，再说明行动，避免只做程序性表态。 |
| 2 | service_outage.md | service_outage | 0.3333 | 0.16 | markdown | ## 影响范围 企业应评估受影响的用户、客户、区域、服务模块、订单或交易范围。影响范围尚未查清时，应使用谨慎表达，并承诺持续同步核查进展。 |
| 3 | crisis_response.md | crisis_response | 0.3333 | 0.16 | json_vector | # 危机回应规范 |

### rag_eval_labor_dispute_001

- difficulty: hard
- expected_source_category: labor_dispute
- actual_source_categories: []
- top1_source_hit: False
- top3_source_hit: False
- context_precision: None
- context_pollution_rate: None
- keyword_hits: []
- fallback_used: False
- failure_reason: no_retrieval_result

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|

### rag_eval_product_recall_001

- difficulty: medium
- expected_source_category: product_recall
- actual_source_categories: ['product_quality', 'food_safety']
- top1_source_hit: False
- top3_source_hit: False
- context_precision: 0.0
- context_pollution_rate: 1.0
- keyword_hits: ['批次', '检测', '用户']
- fallback_used: False
- failure_reason: expected_source_category_not_in_top3

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | product_quality.md | product_quality | 0.2564 | 0.1374 | json_vector | ## 型号与批次核查 涉及实物商品质量、安全隐患、零件脱落、电池异常、漏水或使用不适时，企业应核查具体型号、生产批次、销售渠道和用户反馈范围。回应应避免在事实未查清前直接确认全部问题。 |
| 2 | food_safety.md | food_safety | 0.2079 | 0.107 | json_vector | ## 消费者权益 食品安全危机会直接影响消费者信任。回应中应明确理解消费者担忧，说明投诉受理、批次排查、产品检测和后续进展同步安排。 |

### rag_eval_financial_rumor_001

- difficulty: hard
- expected_source_category: financial_rumor
- actual_source_categories: ['data_privacy', 'data_privacy']
- top1_source_hit: False
- top3_source_hit: False
- context_precision: 0.0
- context_pollution_rate: 1.0
- keyword_hits: ['核实']
- fallback_used: False
- failure_reason: expected_source_category_not_in_top3

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | data_privacy.md | data_privacy | 0.2364 | 0.1174 | json_vector | ## 初步响应 涉及用户个人信息、隐私或数据安全的事件，应先表达重视用户权益和信息安全，说明企业已经启动核查。回应应避免在事实未查清前直接确认泄露范围，也不应简单否认用户担忧。 |
| 2 | data_privacy.md | data_privacy | 0.2074 | 0.1034 | json_vector | ## 受影响数据与用户范围调查 企业应排查可能涉及的数据类型、用户范围、时间窗口和受影响系统。常见信息包括手机号、地址、账号标识、身份信息、位置或人脸等敏感数据。调查结果应以已核实事实为准。 |

### rag_eval_executive_scandal_001

- difficulty: medium
- expected_source_category: executive_scandal
- actual_source_categories: ['crisis_response', 'executive_misconduct', 'executive_misconduct']
- top1_source_hit: False
- top3_source_hit: False
- context_precision: 0.0
- context_pollution_rate: 1.0
- keyword_hits: ['道歉']
- fallback_used: False
- failure_reason: expected_source_category_not_in_top3

| rank | source | category | score | rerank_score | backend | preview |
|---:|---|---|---:|---:|---|---|
| 1 | crisis_response.md | crisis_response | 0.5 | 0.2436 | markdown | ## 初次回应 初次回应应包括关注事件、理解公众担忧、启动核查、持续同步进展。语气应先共情，再说明行动，避免只做程序性表态。 |
| 2 | executive_misconduct.md | executive_misconduct | 0.2751 | 0.2058 | json_vector | ## 组织立场 企业应清晰表达尊重用户、员工和公众的组织立场，说明公司不鼓励歧视、侮辱、傲慢或伤害公众情感的表达。回应应避免只强调个人行为而忽视管理责任。 |
| 3 | executive_misconduct.md | executive_misconduct | 0.2243 | 0.1814 | json_vector | ## 道歉、管理责任与整改 如相关言行确有不当，企业应表达歉意，说明管理责任和改进措施。后续整改可以包括管理培训、沟通机制、内部规范复盘和持续公开进展。 |
