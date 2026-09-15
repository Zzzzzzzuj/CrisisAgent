# P27 Harness Policy Safety Guardrails

P26 证明了 Harness 策略确实会改变 Replay 行为，但策略变化不等于策略更优。P27 增加确定性的 Policy Diff / Risk Analyzer，防止 Candidate 通过降低 Evidence Gate 或 Human Review 来获得表面上的完成率提升。

## 风险分类

- `safe`：增加 timeout/retry，或提高证据分数阈值。
- `review_required`：增加执行预算等需要人工评估的变化。
- `safety_weakening`：降低证据阈值、放宽污染率、关闭 Evidence Gate 审核或关闭 Human Review trigger。

`evidence_conflict` 和 `review_scope_mismatch` 属于关键审核项，Candidate 默认不能关闭。安全弱化会写入 Proposal、Harness metadata 和 Comparison 报告；Replay/Golden gate 还会检查必要人工审核覆盖率不能下降。

高风险 Candidate 即使功能指标没有下降，也不能自动通过。只有评测门槛通过且人工填写明确理由后，才可能进入后续审批；系统不会自动启用、发布或修改 Prompt。

## 面试讲解版

我没有把审核触发率当成越低越好的指标，而是增加了策略差异分析。候选配置如果降低证据门槛或关闭审核，会被标记为安全弱化，关键 trigger 直接禁止修改，Replay 还要验证必要审核覆盖率不能下降。这样 Candidate 的优化目标是提高稳定性，而不是通过少审核来制造更漂亮的指标。
