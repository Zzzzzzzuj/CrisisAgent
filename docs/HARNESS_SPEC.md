# HarnessSpec 版本化运行规范

## 定位

P21 不新增 Agent，也不把 CrisisAgent 改造成自动自优化系统。它把已有的固定 Workflow、工具约束、ContextPack、Legal RAG 和 Human Review 规则收敛为可保存、可追踪的 `HarnessSpec`，用于解释某次运行实际采用了什么配置。

## 映射关系

- `workflow`：复用现有 `AGENT_ORDER` 和 `AGENT_DEPENDENCIES`，默认仍是 Sentiment -> Writer -> RedTeam -> Legal -> Writer V2 -> Decision。
- `prompts`：记录现有 Prompt 的版本引用，不在本阶段自动改 Prompt。
- `skills_tools`：从现有 Skill Registry 的 ToolDefinition 生成 JSON-safe 摘要，并记录 ToolRunner 预算。
- `context_policy`：引用已有 Case Memory、ContextPack 和风险水位线策略。
- `retrieval_policy`：引用 Retrieval Need Gate、Hybrid Search、Reranker 和 Evidence Quality Gate。
- `review_policy`：引用 Human Review Policy、审批范围和禁止自动发布规则。

## 版本与快照

默认 `crisisagent-default@1.0.0` 由当前代码规则生成。动态运行可通过 `harness_id`、`harness_version` 选择已保存版本；不传时保持默认行为。实际快照写入 `AgentState.metadata["harness_spec"]`，因此会随既有 checkpoint 保存，并在 Dynamic trace、AgentRun 和 Report 中保留。

API 提供列表、详情、创建、复制、启用和回滚。创建与启用是离线/人工操作，旧版本不删除；非法配置不能改变默认 Agent 顺序。历史 Run 使用自己的快照，而不是重新读取当前 active 版本。

## 当前边界

JSON Repository 是 MVP 持久化方式。P21 不实现 LLM 自动修改配置、不自动发布配置、不强行接入主 Executor，也不改变旧 `/api/crisis/run` 和 `/api/dynamic/run` 的请求兼容性。前端只提供版本与配置摘要预览。

## 面试讲解版

“我没有把 HarnessSpec 做成一个会自己改生产配置的 Meta-Agent，而是先做版本化运行规范。每次 Run 保存实际生效的 workflow、工具、检索、上下文和审核配置快照，遇到 Bad Case 时可以对照 Trace 和 Eval Center 复盘；新版本先人工创建、启用和回滚，历史运行仍能还原当时配置。这解决的是可追溯和可回滚，而不是用自动化掩盖验证不足。”
# P22.2 Candidate Controlled Evaluation

人工创建的 Harness Candidate 通过 `DRAFT -> EVALUATED -> APPROVED -> ACTIVE` 流程管理。候选只允许改变工具预算/超时/重试、Evidence Gate 阈值和指定 Human Review 触发开关；固定 Workflow、Prompt 和 RAG 算法保持不变。启用前必须通过离线比较门槛并获得人工审批，拒绝和回滚都会保留原因与历史快照。
