# CrisisAgent Retrieval Need Gate Challenge v3 Evaluation

## Experiment Metadata

- experiment: `Retrieval Need Gate v3 Challenge v3 First Evaluation`
- dataset: `evaluation\rag_gate_challenge_v3.json`
- protocol: `evaluation\reports\rag_gate_challenge_v3_protocol.md`
- gate_v3_commit: `996314c`
- challenge_frozen_commit: `1c57086`
- protocol_frozen_commit: `1c57086`
- evaluation_base_commit: `1c57086`
- python_executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- sentence_transformers_version: `5.7.0`
- bge_model: `BAAI/bge-small-zh`
- bge_fallback_used: `False`
- top_k: `5`
- min_rerank_score: `0.1`
- Challenge v3 status: `no longer untouched after this first formal evaluation`
- Gate production input used in this evaluator: `event` only
- Before this first prediction, Gate v3, Challenge v3, and Protocol v3 were not modified.
- Challenge v3 is Gate v3's first frozen holdout validation.
- Gate v1 Challenge v1 FIRST RUN: `FAIL`
- Gate v2 Challenge v2 FIRST RUN: `FAIL`
- Gate v3 results on Challenge v1/v2 are only `post-hoc regression`, not independent validation.

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

- TP: `19`
- TN: `17`
- FP: `3`
- FN: `1`
- TPR: `0.95`
- TNR: `0.85`
- FPR: `0.15`
- FNR: `0.05`
- Accuracy: `0.9`
- hard_negative_reject_rate: `0.8333`
- hard_negative_reject_count: `10 / 12`
- current_incident_positive_pass_rate: `1.0`
- non_current_hard_negative_reject_rate: `0.8333`

## Positive Category TPR

- `food_safety`: `1.0`
- `data_privacy`: `0.75`
- `service_outage`: `1.0`
- `product_quality`: `1.0`
- `executive_misconduct`: `1.0`

## Negative Type Reject Rate

- `unrelated`: `1.0`
- `business_non_crisis`: `0.75`
- `hard_negative`: `0.8333`

## End-to-End Metrics

- Recall@1: `0.65`
- Recall@3: `0.95`
- Recall@5: `0.95`
- Precision@1: `0.325`
- Precision@3: `0.1583`
- Precision@5: `0.095`
- MRR: `0.7917`
- No-hit Accuracy: `0.85`
- Negative no-hit by type: `{'business_non_crisis': 0.75, 'hard_negative': 0.8333, 'unrelated': 1.0}`
- Source Category Match: `0.4933`
- Context Pollution Rate: `0.3733`
- Fallback Count: `0`
- Gate False Negative Count: `1`
- Retrieval Miss Count: `0`
- Retrieval Pollution Count: `17`

## Acceptance Checks

- `positive_tpr`: `PASS`
- `negative_tnr`: `PASS`
- `hard_negative_reject_rate`: `PASS`
- `false_negative_count`: `PASS`
- `hard_negative_reject_count`: `PASS`
- `positive_category_tpr`: `PASS`
- `recall_at_3`: `PASS`
- `no_hit_accuracy`: `PASS`
- Overall Gate Challenge v3 Status: `PASS`

## False Positives

### gate_challenge_v3_business_004

- type: `business_non_crisis`
- category: `business_non_crisis`
- event: 运营团队设计会员积分活动，讨论不同等级用户的兑换权益和节日优惠。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `2`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `ambiguous_enterprise_risk`
- decision_path: `ambiguous_enterprise_risk_allow`
- matched_signals: `['affected_public', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非当前任务，且存在企业风险或用户影响迹象，按 recall-first 策略放行 RAG。

### gate_challenge_v3_hard_negative_002

- type: `hard_negative`
- category: `hard_negative`
- event: 法务培训需要一份个人信息保护法规学习提纲，重点解释数据泄露后的常见责任边界。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `1`
- current_incident: `True`
- current_incident_signals: `['current_response_need']`
- task_intent: `training_learning`
- decision_path: `current_incident_override`
- matched_signals: `['occurred_negative_event', 'response_or_action_required']`
- negative_signals: `['policy_lookup', 'training_learning']`
- reason: 检测到当前正在发生或已经发生的现实风险，current_incident 优先于模板、统计、培训等任务词，放行 RAG。

### gate_challenge_v3_hard_negative_011

- type: `hard_negative`
- category: `hard_negative`
- event: 请分析过去三年服务故障报道的行业趋势，不涉及公司当前系统运行情况。
- expected label: `no_rag`
- predicted need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `1`
- current_incident: `True`
- current_incident_signals: `['concrete_event_occurrence']`
- task_intent: `ambiguous_enterprise_risk`
- decision_path: `current_incident_override`
- matched_signals: `['occurred_negative_event', 'enterprise_context']`
- negative_signals: `['policy_lookup']`
- reason: 检测到当前正在发生或已经发生的现实风险，current_incident 优先于模板、统计、培训等任务词，放行 RAG。


## False Negatives

### gate_challenge_v3_data_privacy_004

- type: `positive_crisis`
- category: `data_privacy`
- event: 多名商家反馈能看到其他店铺的结算明细，运营侧需要整理排查步骤并回应商家群里的追问。
- expected label: `need_rag`
- predicted need_rag: `False`
- intent: `information_lookup`
- decision_score: `2`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `ambiguous_enterprise_risk`
- decision_path: `no_current_incident_no_enterprise_risk`
- matched_signals: `['response_or_action_required']`
- negative_signals: `[]`
- reason: 文本缺少当前现实危机、用户影响或企业处置需求，不触发 RAG。


## Failure Cases

### gate_challenge_v3_food_safety_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 门店试吃活动结束后，几位顾客在群里说同款糕点吃完后胃部不舒服，运营团队正在整理内部检测流程和对外说明。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['service_outage.md', 'food_safety.md', 'product_quality.md']`
- scores: `[0.3845, 0.3835, 0.3957, 0.3831, 0.3864]`
- rerank_scores: `[0.1985, 0.198, 0.1978, 0.1947, 0.1932]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v3_food_safety_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 社区团购配送的冷藏餐盒到货后有异味，多个小区群要求平台说明运输温控情况，目前原因尚未确认。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['service_outage.md', 'food_safety.md', 'product_quality.md']`
- scores: `[0.3864, 0.4026, 0.3951, 0.3943, 0.3811]`
- rerank_scores: `[0.2039, 0.2013, 0.2011, 0.1971, 0.1941]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_v3_food_safety_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 直播卖出的坚果陆续有人反馈包装内有细小硬物，客服需要准备统一回应脚本，并同步质检抽查安排。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['crisis_response.md', 'product_quality.md', 'food_safety.md']`
- scores: `[0.3835, 0.3941, 0.391, 0.3817, 0.3805]`
- rerank_scores: `[0.3537, 0.2078, 0.1991, 0.1908, 0.1903]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_v3_food_safety_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `food_safety`
- event: 某批次饮品到店后出现瓶口黏连和气味异常，店员拍照发给总部，团队要先形成临时口径。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `['food_safety.md', 'product_quality.md', 'executive_misconduct.md']`
- scores: `[0.4093, 0.393, 0.3991, 0.3878, 0.3867]`
- rerank_scores: `[0.2046, 0.2006, 0.1996, 0.198, 0.1933]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_data_privacy_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 用户在订单页短暂看到陌生人的姓名和地址，截图已在社群转发，法务要统计可能受影响范围。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['data_privacy.md', 'service_outage.md', 'legal_risk_rules.md']`
- scores: `[0.3953, 0.3869, 0.3873, 0.3923, 0.3851]`
- rerank_scores: `[0.2169, 0.2165, 0.2013, 0.1961, 0.1925]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `1`

### gate_challenge_v3_data_privacy_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 会员中心改版后，有用户称自己的手机号被绑定到陌生账号，客服正在汇总反馈并准备解释口径。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'crisis_response.md']`
- scores: `[0.3941, 0.3881, 0.3826, 0.38, 0.3765]`
- rerank_scores: `[0.2046, 0.2016, 0.1913, 0.19, 0.1883]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v3_data_privacy_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `data_privacy`
- event: 平台后台发现异常访问记录，同时外部有人展示部分用户资料截图，尚未完成来源确认但需要先准备用户通知。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['data_privacy.md', 'service_outage.md']`
- scores: `[0.4287, 0.4227, 0.413, 0.4151, 0.4062]`
- rerank_scores: `[0.231, 0.228, 0.2165, 0.2142, 0.2031]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_data_privacy_004

- failure_reason: `gate_false_negative`
- type: `positive_crisis`
- category: `data_privacy`
- event: 多名商家反馈能看到其他店铺的结算明细，运营侧需要整理排查步骤并回应商家群里的追问。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_v3_service_outage_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 晚高峰下单页面一直转圈，部分用户重复扣费但订单未生成，技术团队正在整理故障公告文案。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'product_quality.md']`
- scores: `[0.3911, 0.3896, 0.3893, 0.3878, 0.3952]`
- rerank_scores: `[0.2122, 0.2076, 0.2075, 0.2029, 0.1976]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v3_service_outage_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 小程序今天中午打不开，门店排队明显变长，客服要准备临时替代方案说明。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'crisis_response.md', 'product_quality.md']`
- scores: `[0.3872, 0.3962, 0.3814, 0.3878, 0.38]`
- rerank_scores: `[0.2226, 0.2029, 0.2004, 0.1939, 0.19]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_service_outage_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 支付系统恢复前，商户端收款记录与用户扣款记录不同步，目前尚未完成根因定位，需要先发布进展。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md', 'legal_risk_rules.md', 'product_quality.md']`
- scores: `[0.3881, 0.3932, 0.3905, 0.3805, 0.3816]`
- rerank_scores: `[0.2094, 0.2004, 0.1991, 0.1979, 0.1908]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v3_service_outage_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `service_outage`
- event: 客服后台白屏导致热线排队激增，运营负责人要求统计受影响用户并给出恢复时间说明。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['service_outage.md', 'crisis_response.md', 'product_quality.md']`
- scores: `[0.4088, 0.4032, 0.4069, 0.3976, 0.4024]`
- rerank_scores: `[0.2166, 0.2138, 0.2116, 0.2029, 0.2012]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_product_quality_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 同型号充电宝被用户连续反馈外壳鼓起，售后正在准备客服回应脚本和检测流程。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'data_privacy.md']`
- scores: `[0.3928, 0.375, 0.3758, 0.3747, 0.3733]`
- rerank_scores: `[0.2052, 0.2051, 0.2011, 0.1962, 0.1955]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v3_product_quality_002

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 新品耳机上市后有买家称充电盒发热并伴随异味，团队还没确认原因，但需要先安排退换咨询口径。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'food_safety.md', 'data_privacy.md']`
- scores: `[0.3849, 0.3893, 0.3681, 0.3811, 0.3718]`
- rerank_scores: `[0.1961, 0.1946, 0.1914, 0.1905, 0.1896]`
- context_pollution_rate: `0.6667`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_product_quality_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 多位车主反馈同一配件松动，论坛开始整理照片，质量团队需要汇总检测步骤给客服使用。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'service_outage.md']`
- scores: `[0.4142, 0.405, 0.4108, 0.3931, 0.3914]`
- rerank_scores: `[0.2247, 0.2201, 0.2149, 0.206, 0.1957]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `6`

### gate_challenge_v3_product_quality_004

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `product_quality`
- event: 家用净水器安装后出现渗水反馈，多个用户在售后群追问处理安排，品牌需要准备说明。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'data_privacy.md']`
- scores: `[0.3985, 0.3941, 0.3924, 0.3967, 0.3882]`
- rerank_scores: `[0.2118, 0.2096, 0.2045, 0.1983, 0.1941]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v3_executive_misconduct_001

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 公司高管今天在公开活动中的玩笑被剪成短视频传播，评论区出现抵制声音，公关要统计舆情热度。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['crisis_response.md', 'executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.5, 0.4407, 0.4351, 0.4023, 0.4133]`
- rerank_scores: `[0.4, 0.3703, 0.3675, 0.2133, 0.2067]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_v3_executive_misconduct_003

- failure_reason: `wrong_category`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 董事在访谈里的表述被用户认为轻视消费者，品牌尚未确认完整上下文，但需要先制定回应口径。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.4067, 0.3952, 0.4005, 0.3882, 0.3833]`
- rerank_scores: `[0.2183, 0.2089, 0.2078, 0.2054, 0.1916]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_v3_business_004

- failure_reason: `gate_false_positive`
- type: `business_non_crisis`
- category: `business_non_crisis`
- event: 运营团队设计会员积分活动，讨论不同等级用户的兑换权益和节日优惠。
- acceptable_sources: `[]`
- actual_sources: `['service_outage.md', 'product_quality.md', 'data_privacy.md']`
- scores: `[0.3547, 0.3523, 0.3522, 0.3604, 0.3535]`
- rerank_scores: `[0.1824, 0.1812, 0.1811, 0.1802, 0.1767]`
- context_pollution_rate: `1.0`
- intent: `crisis_response_needed`
- decision_score: `2`

### gate_challenge_v3_hard_negative_002

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 法务培训需要一份个人信息保护法规学习提纲，重点解释数据泄露后的常见责任边界。
- acceptable_sources: `[]`
- actual_sources: `['legal_risk_rules.md']`
- scores: `[0.5, 0.5, 0.4305, 0.4272, 0.4104]`
- rerank_scores: `[0.4042, 0.4, 0.3694, 0.3636, 0.3635]`
- context_pollution_rate: `0.0`
- intent: `crisis_response_needed`
- decision_score: `1`

### gate_challenge_v3_hard_negative_011

- failure_reason: `gate_false_positive`
- type: `hard_negative`
- category: `hard_negative`
- event: 请分析过去三年服务故障报道的行业趋势，不涉及公司当前系统运行情况。
- acceptable_sources: `[]`
- actual_sources: `['service_outage.md', 'executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.4129, 0.3966, 0.3946, 0.3934, 0.3913]`
- rerank_scores: `[0.2403, 0.1983, 0.1973, 0.1967, 0.1956]`
- context_pollution_rate: `1.0`
- intent: `crisis_response_needed`
- decision_score: `1`


## Limitations

- This is the first formal prediction run on Challenge v3.
- Challenge v3 first formal result is `PASS` under the pre-registered criteria.
- This is not a perfect result: there are still 3 FP, 1 FN, business reject rate is 0.75, and Context Pollution Rate is 0.3733.
- Challenge v3 is no longer untouched after this report.
- Challenge v3 must not be reused after Gate changes as an independent validation set.
- Gate v3 is frozen for this phase; do not continue developing Gate v4 from this result.
- `retrieval_pollution` means evaluation-level wrong-category/context-pollution quality error, not retrieval exception or BGE fallback.
- Retriever pollution is a separate next-stage retrieval quality problem, not a Gate failure.
- The dataset must not be edited and rerun as an independent holdout.
- Future Gate changes require a new untouched Challenge v4 or another true holdout.
