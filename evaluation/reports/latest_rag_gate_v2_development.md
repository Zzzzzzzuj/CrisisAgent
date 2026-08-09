# CrisisAgent Retrieval Need Gate v2 Development Report

## Scope

- Gate version: `v2 Conservative Reject Gate`
- Production Legal Agent path changed: `False`
- Structured state used: `False`
- BGE / Retriever / KB / Prompt changed: `False`
- Challenge v1 usage: `post-hoc regression only`
- This report must not be described as a new independent Challenge result.

## Historical Baseline

- Gate v1 Challenge v1 FIRST RUN: `TP=4, TN=20, FP=0, FN=16`
- Gate v1 Challenge v1 TPR: `0.20`
- Gate v1 Challenge v1 TNR: `1.00`
- Gate v1 Challenge v1 Status: `FAIL`

## Development Positive

- TP: `15`
- TN: `0`
- FP: `0`
- FN: `0`
- TPR: `1.0`
- TNR: `0.0`
- FPR: `0.0`
- FNR: `0.0`
- hard_negative_reject_rate: `0.0`

## Negative Calibration

- TP: `0`
- TN: `21`
- FP: `3`
- FN: `0`
- TPR: `0.0`
- TNR: `0.875`
- FPR: `0.125`
- FNR: `0.0`
- hard_negative_reject_rate: `0.625`

## Challenge v1 Post-Hoc Regression

- TP: `20`
- TN: `18`
- FP: `2`
- FN: `0`
- TPR: `1.0`
- TNR: `0.9`
- FPR: `0.1`
- FNR: `0.0`
- hard_negative_reject_rate: `0.8`

## Challenge v1 Positive Category TPR

- `data_privacy`: TP=4, FN=0, TPR=1.0
- `executive_misconduct`: TP=4, FN=0, TPR=1.0
- `food_safety`: TP=4, FN=0, TPR=1.0
- `product_quality`: TP=4, FN=0, TPR=1.0
- `service_outage`: TP=4, FN=0, TPR=1.0

## Gate v1 False Negative Recovery

- recovered_false_negatives: `16`
- remaining_false_negatives: `0`
- new_false_positives: `2`

### Original 16 FN Under Gate v2

### gate_challenge_food_safety_001

- category: `food_safety`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['response_or_action_required', 'public_spread', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 多名顾客在食用同批冷藏便当后出现腹痛和呕吐，门店评论区要求品牌给出处理方案。

### gate_challenge_food_safety_002

- category: `food_safety`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 有顾客称奶茶中喝出异物并上传小票和照片，多个门店被追问同批原料是否存在问题。

### gate_challenge_food_safety_003

- category: `food_safety`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['response_or_action_required', 'public_spread', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 连锁餐厅被顾客拍到厨房操作台有虫害痕迹，短视频评论要求企业说明门店卫生管理情况。

### gate_challenge_food_safety_004

- category: `food_safety`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 儿童餐产品被家长反映气味异常，已有家长表示孩子食用后不舒服并要求品牌尽快说明。

### gate_challenge_data_privacy_001

- category: `data_privacy`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `4`
- matched_signals: `['affected_public', 'public_spread', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `['information_lookup']`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 部分用户登录后能看到其他账号的订单、地址和联系方式，截图已在社交平台扩散。

### gate_challenge_data_privacy_002

- category: `data_privacy`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `5`
- matched_signals: `['affected_public', 'public_spread', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 用户收到陌生号码精准报出平台购买记录的骚扰电话，社群质疑平台保护个人信息不力。

### gate_challenge_data_privacy_004

- category: `data_privacy`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 不少用户发现账号头像和昵称被陌生设备改动，怀疑平台登录保护失效并要求给出处理办法。

### gate_challenge_service_outage_001

- category: `service_outage`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['affected_public', 'harm_or_anomaly']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 晚高峰期间大量用户付款后页面一直卡住，商户端订单迟迟不同步，客服排队人数激增。

### gate_challenge_service_outage_002

- category: `service_outage`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 企业云盘连续数小时无法上传合同文件，多个客户项目交付受到影响并要求平台说明恢复时间。

### gate_challenge_service_outage_004

- category: `service_outage`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 医院预约小程序早晨无法取号，患者在大厅排长队并要求运营方解释系统异常原因。

### gate_challenge_product_quality_001

- category: `product_quality`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['affected_public', 'harm_or_anomaly']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 同型号扫地机器人短期内多起充电底座发热，用户晒出照片并询问是否应停止使用。

### gate_challenge_product_quality_002

- category: `product_quality`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 新上市耳机被大量用户反馈佩戴后皮肤红肿，消费者要求品牌说明材质检测情况。

### gate_challenge_product_quality_003

- category: `product_quality`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `6`
- matched_signals: `['affected_public', 'response_or_action_required', 'harm_or_anomaly', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 母婴床护栏被反映卡扣松动，家长担心儿童跌落风险并要求企业给出处理安排。

### gate_challenge_executive_misconduct_002

- category: `executive_misconduct`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `2`
- matched_signals: `['affected_public', 'public_spread']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 区域总监会议发言被员工转发，内容被认为贬低一线人员，内部群和外部评论区持续发酵。

### gate_challenge_executive_misconduct_003

- category: `executive_misconduct`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `4`
- matched_signals: `['affected_public', 'response_or_action_required', 'enterprise_context']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 品牌高层公开评价竞争对手用户群体，引发合作方质疑企业价值观并要求正式说明。

### gate_challenge_executive_misconduct_004

- category: `executive_misconduct`
- expected_need: `True`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `4`
- matched_signals: `['affected_public', 'public_spread', 'harm_or_anomaly']`
- negative_signals: `[]`
- reason: 无法高置信判定为非危机任务，且存在企业现实风险或用户影响，按 recall-first 策略放行 RAG。
- text: 高管私人社交账号发布争议内容后被用户集中转发，多个渠道出现退款和取关声音。


### New FP Under Gate v2

### gate_challenge_hard_negative_008

- category: `hard_negative`
- expected_need: `False`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `3`
- matched_signals: `['occurred_negative_event', 'enterprise_context']`
- negative_signals: `[]`
- reason: 事件包含已发生负面事件，并存在用户影响、传播或回应处置需求，放行 RAG。
- text: 客服主管想统计过去半年投诉类型占比，用于优化服务流程。

### gate_challenge_hard_negative_010

- category: `hard_negative`
- expected_need: `False`
- need_rag: `True`
- intent: `crisis_response_needed`
- decision_score: `1`
- matched_signals: `['occurred_negative_event', 'enterprise_context']`
- negative_signals: `['hypothetical_discussion']`
- reason: 事件包含已发生负面事件，并存在用户影响、传播或回应处置需求，放行 RAG。
- text: 技术团队做演练，想讨论如果未来核心系统出现故障，预案里应该包含哪些角色分工。


## Architecture Changes

- ambiguous enterprise risk defaults to need_rag=true
- only high-confidence negative intent rejects retrieval
- information_lookup requires combined lookup evidence instead of single response words
- decision_score is retained for trace/debug but no longer acts as the sole decision threshold

## Signal / Keyword Expansions

- added harm_or_anomaly signal group
- added enterprise_context signal group
- expanded policy/business/customer-service phrase coverage for high-confidence negative intent

## Risk

- Gate v2 intentionally shifts toward recall-first behavior, so false positives can increase.
- Challenge v1 is no longer untouched and can only guide diagnosis; Gate v2 needs a new Challenge v2 for final validation.