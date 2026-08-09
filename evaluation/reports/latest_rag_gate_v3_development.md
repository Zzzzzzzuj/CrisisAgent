# CrisisAgent Retrieval Need Gate v3 Development Report

## Scope

- Gate version: `v3 Two-Layer Deterministic Gate`
- Production Legal Agent path changed: `False`
- Retriever / BGE / Hybrid / Reranker / Threshold changed: `False`
- Structured state used: `False`
- LLM used: `False`
- Challenge v1/v2 usage: `post-hoc regression only`

## Frozen History

- Gate v1 Challenge v1 FIRST RUN: `FAIL`, TPR=`0.20`, TNR=`1.00`
- Gate v2 Challenge v2 FIRST RUN: `FAIL`, TP=20, TN=16, FP=4, FN=0, TPR=`1.00`, TNR=`0.80`
- Gate v3 results on Challenge v1/v2 must not be described as independent validation.

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
- hard_negative_reject_count: `0`

## Negative Calibration

- TP: `0`
- TN: `23`
- FP: `1`
- FN: `0`
- TPR: `0.0`
- TNR: `0.9583`
- FPR: `0.0417`
- FNR: `0.0`
- hard_negative_reject_rate: `0.875`
- hard_negative_reject_count: `7`

## Challenge v1 Post-Hoc Regression

- TP: `20`
- TN: `20`
- FP: `0`
- FN: `0`
- TPR: `1.0`
- TNR: `1.0`
- FPR: `0.0`
- FNR: `0.0`
- hard_negative_reject_rate: `1.0`
- hard_negative_reject_count: `10`

## Challenge v2 Post-Hoc Regression

- TP: `20`
- TN: `20`
- FP: `0`
- FN: `0`
- TPR: `1.0`
- TNR: `1.0`
- FPR: `0.0`
- FNR: `0.0`
- hard_negative_reject_rate: `1.0`
- hard_negative_reject_count: `12`

## Challenge v2 Positive Category TPR

- `data_privacy`: TP=4, FN=0, TPR=1.0
- `executive_misconduct`: TP=4, FN=0, TPR=1.0
- `food_safety`: TP=4, FN=0, TPR=1.0
- `product_quality`: TP=4, FN=0, TPR=1.0
- `service_outage`: TP=4, FN=0, TPR=1.0

## Gate v2 Challenge v2 FP Recovery

- recovered_false_positives: `4`
- remaining_false_positives: `0`
- new_false_positives: `0`
- new_false_negatives: `0`

### Original 4 FP Under Gate v3

### gate_challenge_v2_hard_negative_004

- category: `hard_negative`
- type: `hard_negative`
- expected_need: `False`
- need_rag: `False`
- intent: `future_hypothetical`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `future_hypothetical`
- decision_path: `non_current_task_reject`
- decision_score: `0`
- matched_signals: `['harm_or_anomaly', 'enterprise_context']`
- negative_signals: `['hypothetical_discussion', 'future_hypothetical']`
- reason: 未检测到当前现实危机，且任务被识别为 future_hypothetical，不触发 RAG。
- text: 产品负责人讨论如果未来出现同款设备过热传闻，客服脚本里应该准备哪些信息。

### gate_challenge_v2_hard_negative_006

- category: `hard_negative`
- type: `hard_negative`
- expected_need: `False`
- need_rag: `False`
- intent: `content_editing`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `content_editing`
- decision_path: `non_current_task_reject`
- decision_score: `0`
- matched_signals: `['occurred_negative_event', 'enterprise_context']`
- negative_signals: `['content_editing']`
- reason: 未检测到当前现实危机，且任务被识别为 content_editing，不触发 RAG。
- text: 请把一份系统故障公告模板改得更清晰，但目前没有真实故障需要发布。

### gate_challenge_v2_hard_negative_011

- category: `hard_negative`
- type: `hard_negative`
- expected_need: `False`
- need_rag: `False`
- intent: `statistics_reporting`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `statistics_reporting`
- decision_path: `non_current_task_reject`
- decision_score: `1`
- matched_signals: `['affected_public', 'public_spread', 'enterprise_context']`
- negative_signals: `['historical_analysis', 'statistics_reporting']`
- reason: 未检测到当前现实危机，且任务被识别为 statistics_reporting，不触发 RAG。
- text: 品牌舆情团队要统计过去一年高管相关讨论热度，区分媒体报道、用户评论和行业文章。

### gate_challenge_v2_hard_negative_012

- category: `hard_negative`
- type: `hard_negative`
- expected_need: `False`
- need_rag: `False`
- intent: `training_learning`
- current_incident: `False`
- current_incident_signals: `[]`
- task_intent: `training_learning`
- decision_path: `non_current_task_reject`
- decision_score: `2`
- matched_signals: `['response_or_action_required', 'enterprise_context']`
- negative_signals: `['training_learning']`
- reason: 未检测到当前现实危机，且任务被识别为 training_learning，不触发 RAG。
- text: 质量部门想整理产品检测流程的内部培训材料，说明抽检、留样和记录保存步骤。


### New FP Under Gate v3

- None

### New FN Under Gate v3

- None

## Architecture Changes

- added explicit Current Incident Detector layer
- added explicit Task Intent Rejector layer
- made precedence explicit: current_incident overrides non-current task words
- kept ambiguous enterprise risk recall-first when no high-confidence non-current task exists

## Signal / Keyword Expansions

- added non-current task intent groups for training, historical analysis, statistics reporting, preparedness, and future hypothetical tasks
- added current incident signals for concrete occurrence, user impact, observed anomaly, public reaction, and response need
- added no-current evidence such as no real incident, future-only, historical-only, and internal-training wording

## Risk

- Gate v3 protects current incident recall by giving current_incident precedence over non-current task words.
- The remaining risk is still false negatives on implicit current incidents that lack enough current/user/anomaly signals.
- Challenge v1/v2 are no longer untouched; Gate v3 needs a new Challenge v3 for final validation.