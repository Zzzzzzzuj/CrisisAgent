# CrisisAgent Interview Pitch

## 30 秒项目介绍

CrisisAgent 是我做的一个企业危机响应 AI Agent 项目。它不是让大模型直接写公关稿，而是把一次危机事件拆成舆情研判、文案生成、红队质疑、法律合规审查、二次修订、最终决策和人工审核。后端用 FastAPI 和自研轻量 Dynamic Runtime，支持 AgentState、Checkpoint/Resume、Legal RAG、Guardrails、Auth/RBAC、PostgreSQL 持久化和 Vue Dashboard 展示。

## 1 分钟项目介绍

CrisisAgent 解决的是“企业遇到食品安全、数据泄露、服务故障等事件时，如何让 AI 生成可审查、可追踪、可恢复的危机回应”。我没有直接套一个外部 Agent 框架，而是在项目里实现了 Planner、Plan Validator、Executor 和 AgentState。每个 Agent 的输入输出都落在共享状态里，trace 记录每一步耗时、输出摘要、错误、RAG 来源和 fallback。

生产化方面，我把最初的 JSON checkpoint 扩展成 repository 接口，支持 PostgreSQL 和 Alembic；新增 async runtime，让 `/api/dynamic/run` 可以返回 queued；加了 Auth/RBAC，让真实审核人 approve/reject 并写 audit log；还加了 LLM timeout/retry、JSON repair、Guardrails、runtime metrics 和 `/ready`。目前定位是 production-ready prototype，不是已经上线的生产服务。

## 3 分钟项目介绍

这个项目的核心思路是：危机公关不是一个单点生成任务，而是一条风险控制链路。用户输入一个危机事件后，系统先做 Sentiment 分析，判断风险等级、公众情绪和关键词；Writer v1 生成第一版声明；RedTeam 模拟公众质疑；Legal Agent 结合 Retrieval Need Gate 和 RAG 做合规审查；Writer v2 根据红队和法律建议改写；Decision Agent 输出最终声明和评分。

Dynamic Runtime 部分我实现了 Planner、Validator、Executor 和 AgentState。Planner 负责生成任务计划，Validator 保证依赖顺序正确，Executor 根据计划执行 Agent，并把结果、trace、失败 Agent 和 approval 状态写入 AgentState。高风险、低评分、LLM fallback 或 Guardrail 命中会进入 Human Review。系统会保存 checkpoint，审核通过后可以从原 session resume。

RAG 部分重点放在 Legal Agent。开始时我发现无关 query 也会返回低分 chunk，所以加了 rerank 后的相关度过滤。后来为了减少无关任务触发 RAG，又做了 Retrieval Need Gate v3，区分“topic 相关”和“当前危机响应意图”。再通过 frozen challenge 和 retrieval holdout 验证 Gate 和 Reranker 的效果。Reranker v2 是手写 domain-aware rule，不是 Cross Encoder，这一点我会明确说明。

生产化阶段我补了 PostgreSQL checkpoint backend、Alembic migration、Auth/RBAC、真实审核人审计、LLM reliability、Guardrails、RAG knowledge ingestion、Observability 和 readiness。最后一轮测试结果是 `437 passed`。真实 DeepSeek + BGE smoke 的结果是 `PASS_WITH_LLM_FALLBACK_OBSERVED`，说明真实模型请求和 BGE 能跑通，但也观察到 structured output 不稳定，所以不能夸大成生产可靠性。

## 面试官可能追问

### 1. 为什么不用 LangGraph 或现成 Agent 框架？

背诵版回答：这个项目主要是为了展示我对 Agent Runtime 的理解，所以我自己实现了 Planner、Validator、Executor、AgentState 和 Checkpoint。这样我能清楚解释状态怎么流转、Agent 结果怎么传递、Human Gate 怎么暂停和恢复。如果在真实团队里需要更复杂编排，我也可以把这些概念迁移到 LangGraph 等框架上。

### 2. Dynamic Runtime 和 Fixed Workflow 有什么区别？

背诵版回答：Fixed Workflow 是固定顺序，适合稳定回归；Dynamic Runtime 是通过 Planner 生成计划，再由 Validator 补齐和校验依赖，Executor 按计划执行。它的好处是所有中间状态都在 AgentState 里，便于 checkpoint、resume、trace 和后续扩展。

### 3. Legal RAG 为什么要加 Retrieval Need Gate？

背诵版回答：因为 topic 相关不等于需要检索。比如“总结个人信息保护法规用于培训”跟数据隐私知识库很相关，但它不是当前危机处置。Gate 的作用是在检索前判断是否存在当前危机响应意图，避免把无关或非当前任务送进 RAG，减少上下文污染。

### 4. RAG 做到了什么程度？

背诵版回答：当前是本地轻量 RAG：Markdown fallback、数据库知识文档导入、chunk 管理、Hash/BGE embedding、Keyword + Vector Hybrid、RuleBasedReranker 和 trace metadata。没有使用 pgvector、ANN、BM25、RRF 或 Cross Encoder。这个项目重点是把 RAG 链路做成可评测和可审计，而不是追求最复杂检索技术。

### 5. 真实 LLM 输出不稳定怎么办？

背诵版回答：LLMClient 做了 timeout、retry、失败分类；parser 做 JSON 提取和修复；字段缺失会触发 schema validation failed。Agent 会 fallback 到 mock 结果，同时 trace 记录 failure_type 和 fallback_used。Human Policy 发现 LLM fallback 后会进入人工审核。

### 6. Human Review 如何做到可审计？

背诵版回答：开启 `AUTH_ENABLED=true` 后，用户通过 JWT 登录，角色分为 operator、legal_reviewer 和 admin。approve/reject 只允许 legal_reviewer 或 admin，审核动作会记录 reviewer_id、reviewer_username、reviewer_role，并写入 audit_logs。

### 7. PostgreSQL 在项目中存什么？

背诵版回答：生产化路径保存 crisis_sessions、agent_checkpoints、agent_traces、approvals、evaluations、audit_logs、users 以及 knowledge_documents/knowledge_chunks。JSON fallback 仍保留，用于本地测试和 demo。

### 8. Async Runtime 是生产级队列吗？

背诵版回答：不是。当前 async 是 in-process ThreadPoolExecutor，能证明异步接口和后台执行模型，但进程重启会丢失尚未执行的内存队列，多进程也不共享。文档里明确下一步应替换 Redis/RQ/Celery。

### 9. 你怎么验证项目不是只跑通一个 demo？

背诵版回答：我做了多层测试和评测。普通 pytest 当前是 437 passed；Evaluation 里有 Response V2、RAG Baseline、Gate Challenge、Reranker Holdout、Final E2E Regression 和 Real Model Smoke。并且我保留了 Gate v1/v2 的失败结果，没有只展示最终好看的数字。

### 10. 这个项目最大的不足是什么？

背诵版回答：第一，async worker 还不是 durable queue；第二，RAG embedding 还没有接 pgvector/ANN；第三，Reranker 是手写规则；第四，真实 LLM 输出仍有结构化不稳定，需要更强的 retry-with-format 或 provider response_format；第五，module-level RAG trace state 在并发下有隔离风险。
