# P23 Bad Case 驱动的 Harness Candidate Proposal

P23 将 P22.1 的确定性失败诊断转换为受控的 Harness Candidate 建议。Proposal 只说明可能需要检查的策略区域和允许字段，不直接修改 HarnessSpec，也不会自动创建 ACTIVE 版本或自动启用配置。

## 流程

```text
failure tag
→ Proposal DRAFT
→ 人工 ACCEPTED / REJECTED
→ copy baseline 为 DRAFT Candidate
→ 仅应用 allowed_patch
→ 复用 P22.2 evaluate
→ 人工 approve
→ enable 或 rollback
```

工具超时/重试耗尽映射到工具预算，Evidence 低置信映射到 Evidence Gate 配置，Evidence conflict 和 review scope mismatch 映射到 Review Policy。Context 超预算或关键字段丢失只给出 `context_policy` 检查建议，不生成自动 Patch。任何 Workflow、Prompt、RAG 算法或降低审核要求的 Patch 都会被拒绝。

Proposal 保存来源 Run、Comparison 或 Replay Case、baseline 版本和 hash、证据引用、风险说明、验证用例、审核人和原因。`ACCEPTED` 只代表人工同意尝试该建议；应用后候选仍处于 `EVALUATED`，必须通过 P22.2 门槛并再次人工审批才能启用。

## 面试讲法

我没有让 Agent 自动修改自己的运行配置，而是把 Bad Case 先转换成结构化 Proposal。Proposal 经过人工接受后，系统才基于 baseline 创建 DRAFT Candidate，并复用当前已有的 Golden Case 评测；Replay Runner 仍是后续计划。这样失败诊断可以推动后续优化，但配置变更仍然受到白名单、评测、人工审批和回滚约束。
