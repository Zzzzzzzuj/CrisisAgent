# Interview Review

## 30 秒

> CrisisAgent 是一个企业舆情监测与危机响应 Agent Harness。企业先配置 Watchlist，系统通过白名单新闻 provider 发现公开线索，经过归并和风险判断后形成 Public Signal、Alert 和 CrisisEvent，再由 Multi-Agent、Legal RAG 和 Human Review 生成可追踪的响应草稿与报告。

## 1 分钟

> 我没有把项目做成一个输入文本就输出公关稿的 one-shot Demo，而是围绕企业真实工作流设计了 Watchlist、受控新闻连接器、事件库、Agent Run、Legal RAG、Trace、Human Review 和报告导出。Watchlist 查询使用确定性规则，采集范围通过白名单、HTTPS、robots、限速、超时和 live-fetch 开关控制。公开信号不会直接自动发布，而是先进入风险告警和人工审核。系统同时有 ToolRunner、队列可靠性和 Eval Center，用来观察工具失败、重复信号、误报和漏报。

## 高频追问

- 为什么是 Agent Harness？因为它管理 Agent 的状态、checkpoint、工具策略、错误恢复、Human Review 和评测，不只是调用模型。
- 为什么用 Workflow？危机响应中的角色依赖和审核顺序明确，高风险节点必须可预测；Dynamic Runtime 负责状态和策略，而不是让模型无限自主发挥。
- Watchlist 如何到 Public Signal？实体、别名、产品和风险词生成有限 query，匹配已登记 provider，采集结果保存摘要、来源、实体和 monitor run metadata。
- RAG 怎么评估？使用 retrieval evaluation、ablation、quality gate 和回归集分别观察命中、污染、证据质量和版本退化。
- 工具失败怎么办？ToolRunner 做 schema 校验、timeout、bounded retry、fallback、预算和结构化错误记录。
- 当前不足？还不是生产级多租户系统，长期运行需要 PostgreSQL、企业 SSO、调度基础设施、规模化限流和更大的验证集。

## P20 追问：多轮危机记忆

- 为什么不是普通聊天记忆？Case Memory 保存的是已完成或审核通过的危机案例摘要，AgentState 负责当前运行，Checkpoint 负责任务恢复，Legal RAG 负责法律知识，职责不同。
- 如何避免第二轮失忆？用 `case_group_id`、`round_index` 和 `previous_memory_id` 串起危机生命周期；确定性 Retriever 优先选择同组、相近轮次和未解决问题。
- 不同 Agent 看到什么？RedTeam 关注上一轮和未解决攻击面，Legal 关注历史法律约束和事实状态，Writer 关注上一轮声明和变化，Decision 关注结果趋势和是否需要二次回应。
- 是否已经改了主 Agent？没有。当前是有数量、长度和敏感字段裁剪的 ContextPack Preview，先独立验证，不改变主 Workflow、Prompt 或 Agent 顺序。
