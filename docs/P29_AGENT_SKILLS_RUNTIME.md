# P29 Agent Skills Runtime Integration

## 定位

P29 将已有业务能力以受控 Skill 的方式接入主流程。它不是任意工具调用，也不是 ReAct 或完全自主规划；Skill Selector 根据 Agent 角色和当前状态使用固定规则选择能力，随后统一交给现有 ToolRunner 执行。

## Skill 定义与白名单

`AgentSkill` 兼容原有 `SkillRegistry`，并补充 `skill_id`、`agent_allowlist`、`preconditions` 和预算元数据。运行时注册四个内部 Skill：

- `event_risk_triage`：只允许 RedTeam，判断风险、来源冲突和优先级；
- `evidence_verification`：只允许 Legal，汇总证据数量、置信度和事实冲突；
- `context_retrieval`：允许 Writer/Legal，复用 P28 已构建的角色化 ContextPack；
- `statement_constraint_check`：只允许 Writer V2，检查未核实事实和法律风险约束。

Selector 输出选择原因和未选择项，并检查 Agent 白名单。没有把这些内部 Skill 加入外部 MCP/HTTP safe tool allowlist，避免内部运行能力意外对外暴露。

## 运行链路

```text
固定 Workflow / Dynamic Runtime
→ ContextPack Runtime Provider
→ Rule-based Skill Selector
→ existing Skill Registry
→ ToolRunner(timeout/retry/fallback/budget)
→ skill_results
→ Agent payload
→ Agent 执行
```

Skill 选择和结果保存在 `AgentState.metadata["skill_selection"]`、`skill_runtime_results`，Dynamic Trace 保存选择摘要和结构化结果；Checkpoint 通过 State metadata 保存，Resume 可以复用同一运行的选择结果和策略快照。固定 Workflow 同样经过统一 step 入口，原六步顺序不变。

## 故障与审核

输入/输出 Schema 不合法、ToolRunner 超时、重试耗尽、权限拒绝或执行异常会变成结构化 `ToolResult` 和 `skill_*` failure tag。失败不会直接抛出打断主流程；结果保留 `human_review_required`，Human Review Policy 可以据此追加审核触发。

Context Retrieval 不重新查询 Case Memory，而是复用 P28 Provider 的 Pack。没有 ContextPack 或 Skill 执行失败时，Agent 仍可使用原有输入继续运行，保持降级行为。

## 当前边界

本阶段只做离线、规则化 Skill 选择，使用 mock Agent 和本地数据验证；没有访问网络、真实 LLM、Redis、PostgreSQL 或 BGE，也没有自动修改 Harness、Prompt、审核策略或发布声明。

## 面试讲解版

之前项目虽然有 Skill Registry 和 ToolRunner，但主要是旁路实验能力。P29 没有让 LLM 自由调用任意工具，而是在 Executor 前增加规则化 Selector：RedTeam 只拿风险 triage，Legal 只拿证据验证和 ContextPack，Writer V2 只做声明约束检查。每个 Skill 都有输入输出 Schema、Agent 白名单和执行约束，统一通过 ToolRunner 运行。这样既体现了 Skills 的编排和治理，又保留了固定 Workflow 的可预测性；即使 Skill 失败，也会留下结构化失败标签并降级继续，而不是让整条危机响应链路崩溃。
