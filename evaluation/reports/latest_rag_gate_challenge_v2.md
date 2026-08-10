# CrisisAgent Retrieval Need Gate Challenge v2 Evaluation

## Experiment Metadata

- experiment: `Retrieval Need Gate v2 Challenge v2 First Evaluation`
- dataset: `evaluation\rag_gate_challenge_v2.json`
- protocol: `evaluation\reports\rag_gate_challenge_v2_protocol.md`
- challenge_frozen_commit: `e50b00f`
- protocol_frozen_commit: `e50b00f`
- gate_v2_commit: `5cc0ee8`
- evaluation_base_commit: `e50b00f`
- python_executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- sentence_transformers_version: `5.7.0`
- bge_model: `BAAI/bge-small-zh`
- bge_fallback_used: `False`
- top_k: `5`
- min_rerank_score: `0.1`
- Challenge v2 status: `no longer untouched after this first formal evaluation`
- Gate production input used in this evaluator: `event` only
- Gate v1 Challenge v1 FIRST RUN: `TPR=0.20, TNR=1.00, Status=FAIL`
- Gate v2 Challenge v1 result is only `post-hoc regression`, not independent validation.

## Dataset

- total_cases: `40`
- positive_case_count: `20`
- negative_case_count: `20`
- positive_category_counts: `{'data_privacy': 4, 'executive_misconduct': 4, 'food_safety': 4, 'product_quality': 4, 'service_outage': 4}`
- negative_type_counts: `{'business_non_crisis': 4, 'hard_negative': 12, 'unrelated': 4}`

## Pre-Registered Acceptance

- Positive TPR >= `0.9`
- Negative TNR >= `0.85`
- Hard Negative Reject Rate >= `0.75`
- Gate FN <= `2 / 20`
- Hard Negative reject count >= `9 / 12`
- Each Positive category TPR >= `0.75`
- BGE + Gate Recall@3 >= `0.63`
- No-hit Accuracy >= `0.85`
- Context Pollution Rate must be reported.

## Gate Metrics

- TP: `20`
- TN: `16`
- FP: `4`
- FN: `0`
- TPR: `1.0`
- TNR: `0.8`
- FPR: `0.2`
- FNR: `0.0`
- Accuracy: `0.9`
- Hard Negative Reject Rate: `0.6667`
- Hard Negative Reject Count: `8 / 12`
- Positive by Category: `{'food_safety': 1.0, 'data_privacy': 1.0, 'service_outage': 1.0, 'product_quality': 1.0, 'executive_misconduct': 1.0}`
- Negative by Type: `{'unrelated': 1.0, 'business_non_crisis': 1.0, 'hard_negative': 0.6667}`
- Negative Reject Counts: `{'unrelated': 4, 'business_non_crisis': 4, 'hard_negative': 8}`

## End-to-End BGE + Gate Metrics

| Metric | Value |
|---|---:|
| Recall@1 | 0.7 |
| Recall@3 | 0.9 |
| Recall@5 | 0.9 |
| Precision@1 | 0.35 |
| Precision@3 | 0.15 |
| Precision@5 | 0.09 |
| MRR | 0.7917 |
| No-hit Accuracy | 0.8 |
| Source Category Match | 0.3953 |
| Context Pollution Rate | 0.4768 |
| Fallback Count | 0 |
| Gate Failure Count | 4 |
| Retrieval Failure Count | 20 |

### Negative No-hit by Type

- `{'business_non_crisis': 1.0, 'hard_negative': 0.6667, 'unrelated': 1.0}`

## Acceptance Result

- status: `FAIL`
- checks: `{'positive_tpr': True, 'negative_tnr': False, 'hard_negative_reject_rate': False, 'false_negative_count': True, 'hard_negative_reject_count': False, 'positive_category_tpr': True, 'recall_at_3': True, 'no_hit_accuracy': False}`
- category_checks: `{'food_safety': True, 'data_privacy': True, 'service_outage': True, 'product_quality': True, 'executive_misconduct': True}`

## False Positives

### gate_challenge_v2_hard_negative_004

- type: `hard_negative`
- category: `hard_negative`
- event: 产品负责人讨论如果未来出现同款设备过热传闻，客服脚本里应该准备哪些信息。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `1`
- matched_signals: `['harm_or_anomaly', 'enterprise_context']`
- negative_signals: `['hypothetical_discussion']`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。

### gate_challenge_v2_hard_negative_006

- type: `hard_negative`
- category: `hard_negative`
- event: 请把一份系统故障公告模板改得更清晰，但目前没有真实故障需要发布。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['occurred_negative_event', 'enterprise_context']`
- negative_signals: `[]`
- reason: 事件包含已发生负面事件，并存在用户影响、传播或回应处置需求，放行 RAG。

### gate_challenge_v2_hard_negative_011

- type: `hard_negative`
- category: `hard_negative`
- event: 品牌舆情团队要统计过去一年高管相关讨论热度，区分媒体报道、用户评论和行业文章。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['affected_public', 'public_spread', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。

### gate_challenge_v2_hard_negative_012

- type: `hard_negative`
- category: `hard_negative`
- event: 质量部门想整理产品检测流程的内部培训材料，说明抽检、留样和记录保存步骤。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['response_or_action_required', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。


## False Negatives

- None

## Failure Cases

### gate_challenge_v2_food_safety_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 新品酸奶上市活动当天，多位家长反馈孩子饮用后腹部不适，社群里开始转发同一批次包装照片并要求品牌说明。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['food_safety.md', 'product_quality.md']`
- scores: `[0.3876, 0.3945, 0.391, 0.3839, 0.3777]`
- rerank_scores: `[0.2002, 0.1973, 0.1955, 0.1951, 0.1888]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `7`

### gate_challenge_v2_food_safety_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 连锁门店促销期间，有顾客称购买的便当打开后气味异常，短视频评论区聚集了大量询问门店处理办法的留言。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['food_safety.md', 'product_quality.md', 'executive_misconduct.md']`
- scores: `[0.3954, 0.3861, 0.3916, 0.3904, 0.3888]`
- rerank_scores: `[0.1977, 0.1964, 0.1958, 0.1952, 0.1944]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v2_food_safety_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 品牌直播间正在介绍新品零食配方时，后台客服陆续收到消费者反馈包装内有异物，主播评论区要求立即回应。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['food_safety.md', 'executive_misconduct.md', 'service_outage.md']`
- scores: `[0.3998, 0.3922, 0.4035, 0.381, 0.3831]`
- rerank_scores: `[0.2097, 0.2059, 0.2018, 0.197, 0.1915]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `7`

### gate_challenge_v2_food_safety_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 社区团购配送的熟食被用户拍到外包装渗液，多个小区群担心运输温控问题，平台需要准备对外解释。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['food_safety.md', 'product_quality.md', 'service_outage.md']`
- scores: `[0.4163, 0.3992, 0.3988, 0.3899, 0.3888]`
- rerank_scores: `[0.2082, 0.2067, 0.1994, 0.195, 0.1944]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_data_privacy_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 用户更新APP后进入个人中心，发现页面短暂显示了其他人的收货地址和电话号码，截图已经在多个群里流传。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['data_privacy.md', 'service_outage.md']`
- scores: `[0.3866, 0.3892, 0.3824, 0.3871, 0.3789]`
- rerank_scores: `[0.2033, 0.1979, 0.1979, 0.1969, 0.1961]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_v2_data_privacy_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 平台会员日刚结束，不少用户收到包含真实订单金额的陌生短信，怀疑交易信息被第三方获取并要求平台解释。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'food_safety.md']`
- scores: `[0.4069, 0.3972, 0.3886, 0.3931, 0.3891]`
- rerank_scores: `[0.2135, 0.2053, 0.201, 0.1966, 0.1946]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_data_privacy_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 企业正在发布新版本功能，同时客服收到反馈称账号资料被陌生设备改动，用户质疑登录保护机制失效。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['crisis_response.md', 'service_outage.md', 'data_privacy.md']`
- scores: `[0.5, 0.4188, 0.4138, 0.4407, 0.4351]`
- rerank_scores: `[0.25, 0.2234, 0.2209, 0.2203, 0.2175]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_data_privacy_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 有博主展示可批量获取平台用户昵称、头像和部分联系方式的操作录屏，用户开始追问影响范围和补救安排。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['data_privacy.md', 'service_outage.md']`
- scores: `[0.3973, 0.3928, 0.3925, 0.3988, 0.3935]`
- rerank_scores: `[0.2055, 0.2032, 0.2031, 0.2028, 0.1968]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_service_outage_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 晚高峰期间，用户付款后页面长时间停留在处理中，商户端订单不同步，客服排队人数快速上升。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'food_safety.md']`
- scores: `[0.3931, 0.3725, 0.3736, 0.3693, 0.3692]`
- rerank_scores: `[0.2042, 0.1939, 0.1906, 0.1885, 0.1884]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_service_outage_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 平台会员活动页面打不开，部分用户重复扣费但权益未到账，社交平台开始集中询问恢复时间。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'product_quality.md']`
- scores: `[0.405, 0.3881, 0.3851, 0.3815, 0.381]`
- rerank_scores: `[0.2143, 0.2019, 0.1925, 0.1908, 0.1905]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_service_outage_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 企业正常发布季度运营数据的同一天，核心小程序连续出现白屏，门店无法核销优惠券并要求总部给出说明。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['data_privacy.md', 'crisis_response.md']`
- scores: `[0.443, 0.4374, 0.4078, 0.4039, 0.4162]`
- rerank_scores: `[0.2293, 0.2187, 0.2183, 0.2164, 0.2159]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `2`

### gate_challenge_v2_service_outage_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 物流查询系统突然无法更新轨迹，用户担心生鲜订单延误变质，客服需要统一回应进展。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'product_quality.md', 'data_privacy.md']`
- scores: `[0.4227, 0.4047, 0.3916, 0.3908, 0.3954]`
- rerank_scores: `[0.2239, 0.2065, 0.2041, 0.1996, 0.1977]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_product_quality_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 同型号儿童座椅在多地用户家中出现卡扣松动，家长群里要求品牌说明是否影响继续使用。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'executive_misconduct.md', 'food_safety.md']`
- scores: `[0.3671, 0.3738, 0.3639, 0.3633, 0.3634]`
- rerank_scores: `[0.1914, 0.1908, 0.1898, 0.1856, 0.1817]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v2_product_quality_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 品牌正在做新品路演时，多名体验用户反馈设备充电后外壳发热并伴随异味，现场视频开始传播。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['crisis_response.md', 'data_privacy.md', 'executive_misconduct.md']`
- scores: `[0.5, 0.4407, 0.4351, 0.4133, 0.4023]`
- rerank_scores: `[0.25, 0.2203, 0.2175, 0.2104, 0.2087]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_product_quality_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 用户集中反映新批次护肤品使用后皮肤红肿，多个达人评论区要求品牌给出检测安排。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'data_privacy.md', 'crisis_response.md', 'food_safety.md']`
- scores: `[0.3956, 0.3986, 0.3836, 0.3869, 0.3861]`
- rerank_scores: `[0.2061, 0.1993, 0.196, 0.1935, 0.193]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `7`

### gate_challenge_v2_product_quality_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 家电售后渠道一天内收到大量同款产品冒烟反馈，区域经理需要准备对外口径和用户处置方案。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'data_privacy.md', 'food_safety.md']`
- scores: `[0.3951, 0.3957, 0.4022, 0.3908, 0.3925]`
- rerank_scores: `[0.2126, 0.2091, 0.2011, 0.1991, 0.1963]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v2_executive_misconduct_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 高管在行业圆桌中的一句评价被剪成短视频，用户认为其轻视消费者权益，品牌评论区出现大量抵制留言。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['executive_misconduct.md', 'food_safety.md', 'crisis_response.md']`
- scores: `[0.4016, 0.3946, 0.3801, 0.3851, 0.375]`
- rerank_scores: `[0.2156, 0.2053, 0.2037, 0.1971, 0.1875]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_executive_misconduct_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 公司宣布合作项目后，负责人早年公开发言被重新翻出，合作方要求确认企业立场和后续处理。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['executive_misconduct.md', 'legal_risk_rules.md', 'product_quality.md', 'crisis_response.md']`
- scores: `[0.3983, 0.3844, 0.3877, 0.3817, 0.3862]`
- rerank_scores: `[0.211, 0.204, 0.2017, 0.1987, 0.1931]`
- context_pollution_rate: `0.25`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_executive_misconduct_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 直播采访中管理层回应用户问题时语气强硬，录屏在社交平台扩散，客服收到大量要求道歉的留言。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['crisis_response.md', 'executive_misconduct.md', 'service_outage.md']`
- scores: `[0.4013, 0.4089, 0.3987, 0.3906, 0.3943]`
- rerank_scores: `[0.3628, 0.2118, 0.2103, 0.2063, 0.1971]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v2_executive_misconduct_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 门店员工称区域负责人在内部会上使用歧视性表述，相关录音被传到本地社区论坛并引发质疑。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['crisis_response.md', 'executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.5, 0.4351, 0.4407, 0.4023, 0.4133]`
- rerank_scores: `[0.2537, 0.2213, 0.2203, 0.2162, 0.2067]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v2_hard_negative_004

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 产品负责人讨论如果未来出现同款设备过热传闻，客服脚本里应该准备哪些信息。
- acceptable_sources: `[]`
- actual_sources: `['data_privacy.md', 'executive_misconduct.md', 'product_quality.md', 'crisis_response.md']`
- scores: `[0.3977, 0.3903, 0.387, 0.385, 0.3845]`
- rerank_scores: `[0.2033, 0.1951, 0.1935, 0.1925, 0.1923]`
- context_pollution_rate: `0.75`
- intent: `crisis_response_needed`
- decision_score: `1`

### gate_challenge_v2_hard_negative_006

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 请把一份系统故障公告模板改得更清晰，但目前没有真实故障需要发布。
- acceptable_sources: `[]`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'executive_misconduct.md']`
- scores: `[0.3906, 0.3902, 0.3951, 0.3843, 0.3866]`
- rerank_scores: `[0.2074, 0.2003, 0.1976, 0.1973, 0.1933]`
- context_pollution_rate: `1.0`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_v2_hard_negative_011

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 品牌舆情团队要统计过去一年高管相关讨论热度，区分媒体报道、用户评论和行业文章。
- acceptable_sources: `[]`
- actual_sources: `['crisis_response.md', 'executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.5, 0.4407, 0.4351, 0.4023, 0.4133]`
- rerank_scores: `[0.4, 0.3703, 0.3675, 0.215, 0.2108]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_v2_hard_negative_012

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 质量部门想整理产品检测流程的内部培训材料，说明抽检、留样和记录保存步骤。
- acceptable_sources: `[]`
- actual_sources: `['product_quality.md', 'executive_misconduct.md']`
- scores: `[0.4125, 0.4179, 0.3983, 0.383, 0.3834]`
- rerank_scores: `[0.2259, 0.2241, 0.2143, 0.2051, 0.2008]`
- context_pollution_rate: `1.0`
- intent: `crisis_response_needed`
- decision_score: `3`


## Limitations

- This is the first formal prediction run on Challenge v2.
- Challenge v2 is no longer untouched after this report.
- `Retrieval Failure Count` means evaluation-level wrong-category or context-pollution quality errors; it does not mean a retrieval exception, BGE fallback, or pipeline crash.
- Challenge v2 overall status is `FAIL`; Positive TPR=`1.0` and Recall@3=`0.9` must not be described as overall success.
- The dataset must not be edited and rerun as an independent holdout.
- If Gate changes are made later, a new Challenge v3 or another untouched holdout is required.
