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

生产化阶段我补了 PostgreSQL checkpoint backend、Alembic migration、Auth/RBAC、真实审核人审计、LLM reliability、Guardrails、RAG knowledge ingestion、Observability 和 readiness。最后一轮测试结果是 `447 passed`。真实 DeepSeek + BGE smoke 的结果是 `PASS_WITH_LLM_FALLBACK_OBSERVED`，说明真实模型请求和 BGE 能跑通，但也观察到 structured output 不稳定，所以不能夸大成生产可靠性。

## 面试官可能追问

### 1. 为什么不用 LangGraph 或现成 Agent 框架？

背诵版回答：这个项目主要是为了展示我对 Agent Runtime 的理解，所以我自己实现了 Planner、Validator、Executor、AgentState 和 Checkpoint。这样我能清楚解释状态怎么流转、Agent 结果怎么传递、Human Gate 怎么暂停和恢复。如果在真实团队里需要更复杂编排，我也可以把这些概念迁移到 LangGraph 等框架上。

### 2. Dynamic Runtime 和 Fixed Workflow 有什么区别？

背诵版回答：Fixed Workflow 是固定顺序，适合稳定回归；Dynamic Runtime 是通过 Planner 生成计划，再由 Validator 补齐和校验依赖，Executor 按计划执行。它的好处是所有中间状态都在 AgentState 里，便于 checkpoint、resume、trace 和后续扩展。

### 3. Legal RAG 为什么要加 Retrieval Need Gate？

背诵版回答：因为 topic 相关不等于需要检索。比如“总结个人信息保护法规用于培训”跟数据隐私知识库很相关，但它不是当前危机处置。Gate 的作用是在检索前判断是否存在当前危机响应意图，避免把无关或非当前任务送进 RAG，减少上下文污染。

### 4. RAG 做到了什么程度？

背诵版回答：当前是本地轻量 RAG：Markdown fallback、数据库知识文档导入、chunk 管理、Hash/BGE embedding、Keyword + Vector Hybrid、RuleBasedReranker 和 trace metadata。默认向量存储仍是 JSON/list，Phase 12 补了可选 pgvector backend，但普通 demo 和 pytest 不依赖它；我没有使用 BM25、RRF 或 Cross Encoder。这个项目重点是把 RAG 链路做成可评测和可审计，而不是追求最复杂检索技术。

### 4.1 知识库治理做到了什么？

背诵版回答：我把知识库从“能导入”补到“可治理”：文档有 `status`、`is_enabled`、`version`、`source_category`、`source_name` 等字段。Legal RAG 默认只检索 `published + enabled` 的文档，draft 和 disabled 会保留审计但不会进检索上下文；trace 里也会带 `document_status`、`is_enabled` 和 `source_name`，便于解释证据来源。

### 5. 怎么证明 RAG 有用？

背诵版回答：我不会只看最终回答来证明 RAG 有用，因为最终文本可能只是模型自己写得像。我的验证分三层：第一层看 trace，Legal Agent 会记录 `rag_used`、`retrieval_backend`、`retrieval_query`、`evidence_chunks`、chunk_id、document_id、version、score、rerank_score 和 `evidence_summary`。第二层跑 `scripts/evaluate_rag_retrieval.py`，只评估 retriever 是否命中期望 source category 和关键词证据。第三层做 ablation：`scripts/run_rag_ablation_demo.py` 对同一个 case 分别运行 `RAG_ENABLED=false/true`，对比 `legal_risks`、`safe_points`、`final_statement`、guardrail 和 evaluation score。这样能证明 RAG evidence 真的进入了审核链路，而不是只展示一个好看的回答。

### 5.1 检索失败以后怎么迭代？

背诵版回答：我没有只保留成功 demo。Phase 14 的 retrieval evaluation 发现 false_advertising、labor_dispute、financial_rumor 等类别命中不足后，我把它们沉淀到 `data/rag_bad_cases.json`，每条记录 failure_type、root_cause、suggested_fix 和 linked_test_case。然后用 `scripts/analyze_rag_bad_cases.py` 生成 bad case report，判断问题是知识缺失、query rewrite、embedding、reranker 还是 metadata filter。知识更新后再跑 `scripts/run_knowledge_ingestion_regression.py`，验证 published/enabled 能检索、draft/disabled 不检索、chunk metadata 和 fallback 都正常。

### 6. 真实 LLM 输出不稳定怎么办？

背诵版回答：LLMClient 做了 timeout、retry、失败分类；parser 做 JSON 提取和修复；字段缺失会触发 schema validation failed。Agent 会 fallback 到 mock 结果，同时 trace 记录 failure_type 和 fallback_used。Human Policy 发现 LLM fallback 后会进入人工审核。

### 7. Human Review 如何做到可审计？

背诵版回答：开启 `AUTH_ENABLED=true` 后，用户通过 JWT 登录，角色分为 operator、legal_reviewer 和 admin。approve/reject 只允许 legal_reviewer 或 admin，审核动作会记录 reviewer_id、reviewer_username、reviewer_role，并写入 audit_logs。

### 8. PostgreSQL 在项目中存什么？

背诵版回答：生产化路径保存 crisis_sessions、agent_checkpoints、agent_traces、approvals、evaluations、audit_logs、users 以及 knowledge_documents/knowledge_chunks。JSON fallback 仍保留，用于本地测试和 demo。

### 9. Async Runtime 是生产级队列吗？

背诵版回答：默认不是。默认 async 是 in-process ThreadPoolExecutor，适合本地 demo；Phase 11 我又补了可选 Redis + RQ backend，可以把任务放进 Redis 队列并用独立 worker 消费。但我不会夸成完整生产队列体系，因为还没有做 dead-letter queue、worker autoscaling 和完整线上部署。

### 10. Function Calling、MCP、Skill、A2A 有什么区别？

背诵版回答：我在项目里补了一层轻量 Skill abstraction。`AgentSkill` 是项目内部的能力描述，比如 `legal_rag_search`、`session_lookup`、`runtime_metrics_query`、`guardrail_check`。Function Calling 是把这些 skill 暴露给 LLM 的 schema，告诉模型能调什么函数、参数是什么；MCP 更像 Agent 连接外部 tool/resource server 的协议，所以我做了 MCP-compatible mock adapter，但没有接真实 MCP SDK；A2A 是 Agent 和 Agent 之间交换任务和上下文，项目里用 `AgentMessage` 表达这个 schema。简单说：Function Calling 偏模型调函数，MCP 偏 Agent 调工具/资源，Skill 是项目内部能力抽象，A2A 是 Agent 间通信。

### 11. fast / standard / strict 推理模式怎么设计？

背诵版回答：我没有直接重写 workflow，而是先做了一个 reasoning mode selector。它根据 risk_level、guardrail_triggered、RAG evidence 数量和置信度、LLM fallback、用户是否要求严格审核来选择 fast、standard 或 strict。fast 用于低风险轻量处理；standard 走正常多 Agent 流程；strict 用于高风险或不稳定输出，建议强制 Legal RAG、Guardrail 和 Human Review。当前它作为 AgentState metadata 和 API 返回中的 planning hint，不破坏原来的 `/api/dynamic/run`。

### 12. 多轮 follow-up 怎么利用 session state？

背诵版回答：我新增了 `/api/dynamic/{session_id}/followup`，它不是重新跑一遍 Agent，而是读取已有 session 的 original event、final_statement、scores、agent_trace、RAG evidence 和 guardrail metadata，生成 clarification、rewrite、media_qna、internal_action、regulator_response 这几类 mock follow-up。这样可以解释多轮对话不是无状态聊天，而是基于同一个 crisis session 的上下文继续处理。

### 13. 长文本生成为什么不直接一次性生成？

背诵版回答：长文本我会拆成 outline、分段生成、consistency check、final merge、guardrail、human review。特别是危机声明这种高风险文本，不能一边 streaming 一边直接给最终稿，因为后面可能出现法律措辞或事实定性问题。SSE 更适合展示进度，不应该替代最终审核。

### 14. 你怎么验证项目不是只跑通一个 demo？

背诵版回答：我做了多层测试和评测。普通 pytest 当前是 491 passed；Evaluation 里有 Response V2、RAG Baseline、RAG Retrieval Eval、RAG Bad Case Loop、Knowledge Ingestion Regression、Gate Challenge、Reranker Holdout、Final E2E Regression 和 Real Model Smoke。并且我保留了 Gate v1/v2 的失败结果，没有只展示最终好看的数字。

### 15. 这个项目最大的不足是什么？

背诵版回答：第一，async 默认仍是 in-process，Redis + RQ 是可选增强但还没有 dead-letter queue；第二，pgvector 只是可选 backend，还没有做 ANN 对照和生产压测；第三，Reranker 是手写规则；第四，真实 LLM 输出仍有结构化不稳定，需要更强的 retry-with-format 或 provider response_format；第五，module-level RAG trace state 仍需继续收敛。
