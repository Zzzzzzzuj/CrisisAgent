# CrisisAgent Retrieval Need Gate Challenge v1 Evaluation

## Experiment Metadata

- experiment: `Retrieval Need Gate Challenge v1`
- dataset: `evaluation\rag_gate_challenge_v1.json`
- protocol: `evaluation\reports\rag_gate_challenge_protocol.md`
- challenge_frozen_commit: `27d3fe1`
- protocol_frozen_commit: `27d3fe1`
- evaluation_base_commit: `27d3fe1`
- python_executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- bge_model: `BAAI/bge-small-zh`
- bge_fallback_used: `False`
- top_k: `5`
- min_rerank_score: `0.1`
- Challenge v1 status: `no longer untouched after this first formal evaluation`
- Gate production input used in this evaluator: `event` only
- Challenge result: `FAIL`
- Failure is mainly caused by `gate_false_negative`.
- Failure is not caused by BGE fallback, retrieval exception, or Knowledge Base loading error.

## Dataset

- total_cases: `40`
- positive_case_count: `20`
- negative_case_count: `20`
- positive_category_counts: `{'data_privacy': 4, 'executive_misconduct': 4, 'food_safety': 4, 'product_quality': 4, 'service_outage': 4}`
- negative_type_counts: `{'business_non_crisis': 5, 'hard_negative': 10, 'unrelated': 5}`

## Pre-Registered Acceptance

- Positive TPR >= `0.9`
- Negative TNR >= `0.85`
- Hard Negative Reject Rate >= `0.8`
- BGE + Gate Recall@3 >= `0.63`
- No-hit Accuracy >= `0.85`
- Context Pollution Rate must be reported.

## Gate Metrics

- TP: `4`
- TN: `20`
- FP: `0`
- FN: `16`
- TPR: `0.2`
- TNR: `1.0`
- FPR: `0.0`
- FNR: `0.8`
- Accuracy: `0.6`
- Hard Negative Reject Rate: `1.0`
- Positive by Category: `{'food_safety': 0.0, 'data_privacy': 0.25, 'service_outage': 0.25, 'product_quality': 0.25, 'executive_misconduct': 0.25}`
- Negative by Type: `{'unrelated': 1.0, 'business_non_crisis': 1.0, 'hard_negative': 1.0}`

## End-to-End BGE + Gate Metrics

| Metric | Value |
|---|---:|
| Recall@1 | 0.05 |
| Recall@3 | 0.2 |
| Recall@5 | 0.2 |
| Precision@1 | 0.025 |
| Precision@3 | 0.0333 |
| Precision@5 | 0.02 |
| MRR | 0.125 |
| No-hit Accuracy | 1.0 |
| Source Category Match | 0.8511 |
| Context Pollution Rate | 0.1064 |
| Fallback Count | 0 |

## Acceptance Result

- status: `FAIL`
- checks: `{'positive_tpr': False, 'negative_tnr': True, 'hard_negative_reject_rate': True, 'no_large_scale_positive_category_rejection': False, 'recall_at_3': False, 'no_hit_accuracy': True}`
- Challenge v1 did not meet the pre-registered Positive TPR >= `0.90` criterion.
- Challenge v1 did not meet the pre-registered End-to-End Recall@3 >= `0.63` criterion.
- This is a formal `FAIL` result. It must not be described as success only because TNR and No-hit Accuracy are both `1.0`.

## False Positives

- None

## False Negatives

### gate_challenge_food_safety_001

- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 多名顾客在食用同批冷藏便当后出现腹痛和呕吐，门店评论区要求品牌给出处理方案。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['response_or_action_required']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_food_safety_002

- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 有顾客称奶茶中喝出异物并上传小票和照片，多个门店被追问同批原料是否存在问题。
- intent: `information_lookup`
- decision_score: `0`
- matched_signals: `[]`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_food_safety_003

- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 连锁餐厅被顾客拍到厨房操作台有虫害痕迹，短视频评论要求企业说明门店卫生管理情况。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['response_or_action_required', 'public_spread']`
- negative_signals: `['information_lookup']`
- reason: 事件更接近 information_lookup，不属于当前危机响应/合规知识检索需求。

### gate_challenge_food_safety_004

- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 儿童餐产品被家长反映气味异常，已有家长表示孩子食用后不舒服并要求品牌尽快说明。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `['information_lookup']`
- reason: 事件更接近 information_lookup，不属于当前危机响应/合规知识检索需求。

### gate_challenge_data_privacy_001

- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 部分用户登录后能看到其他账号的订单、地址和联系方式，截图已在社交平台扩散。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_data_privacy_002

- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 用户收到陌生号码精准报出平台购买记录的骚扰电话，社群质疑平台保护个人信息不力。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_data_privacy_004

- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 不少用户发现账号头像和昵称被陌生设备改动，怀疑平台登录保护失效并要求给出处理办法。
- intent: `information_lookup`
- decision_score: `3`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_service_outage_001

- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 晚高峰期间大量用户付款后页面一直卡住，商户端订单迟迟不同步，客服排队人数激增。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_service_outage_002

- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 企业云盘连续数小时无法上传合同文件，多个客户项目交付受到影响并要求平台说明恢复时间。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `['information_lookup']`
- reason: 事件更接近 information_lookup，不属于当前危机响应/合规知识检索需求。

### gate_challenge_service_outage_004

- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 医院预约小程序早晨无法取号，患者在大厅排长队并要求运营方解释系统异常原因。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['response_or_action_required']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_product_quality_001

- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 同型号扫地机器人短期内多起充电底座发热，用户晒出照片并询问是否应停止使用。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_product_quality_002

- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 新上市耳机被大量用户反馈佩戴后皮肤红肿，消费者要求品牌说明材质检测情况。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `['information_lookup']`
- reason: 事件更接近 information_lookup，不属于当前危机响应/合规知识检索需求。

### gate_challenge_product_quality_003

- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 母婴床护栏被反映卡扣松动，家长担心儿童跌落风险并要求企业给出处理安排。
- intent: `information_lookup`
- decision_score: `3`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_executive_misconduct_002

- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 区域总监会议发言被员工转发，内容被认为贬低一线人员，内部群和外部评论区持续发酵。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。

### gate_challenge_executive_misconduct_003

- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 品牌高层公开评价竞争对手用户群体，引发合作方质疑企业价值观并要求正式说明。
- intent: `information_lookup`
- decision_score: `2`
- matched_signals: `['affected_public', 'response_or_action_required']`
- negative_signals: `['information_lookup']`
- reason: 事件更接近 information_lookup，不属于当前危机响应/合规知识检索需求。

### gate_challenge_executive_misconduct_004

- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 高管私人社交账号发布争议内容后被用户集中转发，多个渠道出现退款和取关声音。
- intent: `information_lookup`
- decision_score: `1`
- matched_signals: `['affected_public']`
- negative_signals: `[]`
- reason: 事件文本缺少已发生风险、公众影响和企业回应处置信号，不触发 RAG。


## Failure Cases

### gate_challenge_food_safety_001

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 多名顾客在食用同批冷藏便当后出现腹痛和呕吐，门店评论区要求品牌给出处理方案。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_food_safety_002

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 有顾客称奶茶中喝出异物并上传小票和照片，多个门店被追问同批原料是否存在问题。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `0`

### gate_challenge_food_safety_003

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 连锁餐厅被顾客拍到厨房操作台有虫害痕迹，短视频评论要求企业说明门店卫生管理情况。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_food_safety_004

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `food_safety`
- event: 儿童餐产品被家长反映气味异常，已有家长表示孩子食用后不舒服并要求品牌尽快说明。
- acceptable_sources: `['food_safety.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_data_privacy_001

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 部分用户登录后能看到其他账号的订单、地址和联系方式，截图已在社交平台扩散。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`

### gate_challenge_data_privacy_002

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 用户收到陌生号码精准报出平台购买记录的骚扰电话，社群质疑平台保护个人信息不力。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`

### gate_challenge_data_privacy_003

- failure_reason: `wrong_category`
- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 某APP被曝存在接口漏洞，疑似可批量查询用户手机号，用户要求平台解释影响范围。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `['service_outage.md', 'data_privacy.md']`
- scores: `[0.4078, 0.4118, 0.4117, 0.4109, 0.4064]`
- rerank_scores: `[0.218, 0.2153, 0.2152, 0.2148, 0.2032]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_data_privacy_004

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `data_privacy`
- event: 不少用户发现账号头像和昵称被陌生设备改动，怀疑平台登录保护失效并要求给出处理办法。
- acceptable_sources: `['data_privacy.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `3`

### gate_challenge_service_outage_001

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 晚高峰期间大量用户付款后页面一直卡住，商户端订单迟迟不同步，客服排队人数激增。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`

### gate_challenge_service_outage_002

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 企业云盘连续数小时无法上传合同文件，多个客户项目交付受到影响并要求平台说明恢复时间。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_service_outage_003

- failure_reason: `wrong_category`
- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 在线教育平台直播课中断，家长集中投诉退费和补课安排，相关话题开始在社群发酵。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `['executive_misconduct.md', 'service_outage.md', 'product_quality.md', 'crisis_response.md']`
- scores: `[0.3798, 0.3781, 0.3753, 0.378, 0.3772]`
- rerank_scores: `[0.1942, 0.1933, 0.1919, 0.189, 0.1886]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `3`

### gate_challenge_service_outage_004

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `service_outage`
- event: 医院预约小程序早晨无法取号，患者在大厅排长队并要求运营方解释系统异常原因。
- acceptable_sources: `['service_outage.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_product_quality_001

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 同型号扫地机器人短期内多起充电底座发热，用户晒出照片并询问是否应停止使用。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`

### gate_challenge_product_quality_002

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 新上市耳机被大量用户反馈佩戴后皮肤红肿，消费者要求品牌说明材质检测情况。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_product_quality_003

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 母婴床护栏被反映卡扣松动，家长担心儿童跌落风险并要求企业给出处理安排。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `3`

### gate_challenge_product_quality_004

- failure_reason: `wrong_category`
- label: `need_rag`
- type: `positive_crisis`
- category: `product_quality`
- event: 电动牙刷某批次出现机身进水后冒烟投诉，用户要求品牌公布检测和退换方案。
- acceptable_sources: `['product_quality.md']`
- actual_sources: `['product_quality.md', 'food_safety.md']`
- scores: `[0.389, 0.4039, 0.3814, 0.389, 0.3871]`
- rerank_scores: `[0.2127, 0.2019, 0.1952, 0.1945, 0.1935]`
- context_pollution_rate: `0.5`
- intent: `crisis_response_needed`
- decision_score: `5`

### gate_challenge_executive_misconduct_001

- failure_reason: `wrong_category`
- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 公司负责人在直播中嘲笑用户投诉，录屏在社交平台传播后大量用户表示抵制。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `['crisis_response.md', 'executive_misconduct.md', 'data_privacy.md']`
- scores: `[0.5, 0.4407, 0.4351, 0.4023, 0.4133]`
- rerank_scores: `[0.25, 0.2203, 0.2175, 0.2152, 0.2113]`
- context_pollution_rate: `0.3333`
- intent: `crisis_response_needed`
- decision_score: `4`

### gate_challenge_executive_misconduct_002

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 区域总监会议发言被员工转发，内容被认为贬低一线人员，内部群和外部评论区持续发酵。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`

### gate_challenge_executive_misconduct_003

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 品牌高层公开评价竞争对手用户群体，引发合作方质疑企业价值观并要求正式说明。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `2`

### gate_challenge_executive_misconduct_004

- failure_reason: `gate_false_negative`
- label: `need_rag`
- type: `positive_crisis`
- category: `executive_misconduct`
- event: 高管私人社交账号发布争议内容后被用户集中转发，多个渠道出现退款和取关声音。
- acceptable_sources: `['executive_misconduct.md']`
- actual_sources: `[]`
- scores: `[]`
- rerank_scores: `[]`
- context_pollution_rate: `0.0`
- intent: `information_lookup`
- decision_score: `1`


## Notes

- This is the first formal prediction run on Challenge v1.
- The Challenge v1 dataset must not be edited and rerun as untouched after this report.
- Challenge v1 can be used for failure analysis after this run, but it can no longer be used as an independent generalization validation set for a modified Gate.
- If a Gate v2 is developed, a new untouched Challenge v2 is required for final validation.
- If the result fails, later Gate changes require a new holdout such as Challenge v2.
