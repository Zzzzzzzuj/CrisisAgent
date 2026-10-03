# Harness 受控迭代 Demo

本文记录项目早期、针对 `tool_timeout` Bad Case 的历史 Harness Golden Case demo。该阶段的 Replay Runner 尚未完成，因此文中的 Replay Case 当时只作为来源标识和后续验证计划保存；这仅描述该历史 demo，不代表当前整个项目没有 Replay 能力。

## 1. Failure Diagnosis

输入已有 Trace/ToolRunner 结果：

```json
{
  "failure_tags": ["tool_timeout"],
  "diagnosis_summary": "tool execution exceeded the configured timeout",
  "evidence_refs": ["trace-17", "tool-4"],
  "recommended_harness_areas": ["tools_policy"]
}
```

Analyzer 只做确定性分类和定位，不修改 HarnessSpec。

## 2. 创建 Proposal

```http
POST /api/harness-proposals
```

请求包含 `baseline_harness_id`、`baseline_version`、`source_run_id`、`replay_case_id` 和诊断结果。系统保存 baseline `spec_hash`，Proposal 状态为 `DRAFT`。

## 3. 人工接受

```http
POST /api/harness-proposals/{proposal_id}/accept
```

人工审核后状态变为 `ACCEPTED`。未接受时调用 apply 返回 `409`，不会创建 Candidate。

## 4. 应用受控 Patch

```http
POST /api/harness-proposals/{proposal_id}/apply
```

系统重新计算当前 baseline 的 `spec_hash`。一致时，从 baseline 复制一个 Candidate，只应用白名单字段，例如：

```text
skills_tools.execution_budget.max_retries: 1 → 2
```

Candidate 记录 `parent_version`、`proposal_id`、`changed_fields`，然后进入 `EVALUATED`。如果 baseline 已变化，apply 返回 `409`，要求重新创建 Proposal。

## 5. Golden Case Evaluation

该历史 demo 当时调用已有 Harness Comparison 和 Eval Center 的离线 Golden Cases：

```text
POST /api/harnesses/{harness_id}/{version}/evaluate
```

同一批 Golden Cases 对比 baseline 和 candidate，并保存 `comparison_id`、两侧 `spec_hash`、指标差异和门槛结果。该 `tool_timeout` demo 当时没有执行真实 Replay Evaluation。

## 6. 人工审批与启用

```http
POST /api/harnesses/{harness_id}/{version}/approve
POST /api/harnesses/{harness_id}/{version}/enable
```

只有评测通过且人工审批后，Candidate 才能从 `APPROVED` 变为 `ACTIVE`。未审批时 enable 返回 `409`。

## 7. 回滚

启用新版本后，旧版本仍保留为已批准版本：

```http
POST /api/harnesses/{previous_harness_id}/{previous_version}/rollback
```

系统恢复旧版本为 `ACTIVE`，不删除任何历史 Proposal、Comparison 或审批记录。重复 approve、enable、rollback 到相同状态时保持幂等。

## 8. 可追溯字段

整条链路关联：

```text
failure_tags
→ proposal_id
→ baseline_harness_id/version/spec_hash
→ candidate_harness_id/version
→ comparison_id
→ approval reviewer/time/reason
```

关键状态为：

```text
DRAFT → ACCEPTED → EVALUATED → APPROVED → ACTIVE
                                      ↓
                                  ROLLED_BACK
```

## 面试讲解版

我没有让 Agent 自动修改自己的运行配置，而是把 Bad Case 转成结构化 Proposal，并通过评测与人工审批控制 Candidate 生命周期。本节只讲项目早期 `tool_timeout` Golden Case demo 的范围。

## Current Status Note

后续项目已具备 `Bad Case → Candidate → Trigger Replay → Frozen Regression → Safety Gate → Human Approval / Reject` 的受控验证路径。RV-004 中 Candidate 的局部改进未能通过整体结果判断，Comparison 为 `UNKNOWN`，Candidate 被 `REJECTED`，Active Harness 版本保持不变。这说明候选修改可以被实验否决；它不是 self-training 或 autonomous self-evolution。
