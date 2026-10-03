# CrisisAgent Interview Pitch

## 30 秒项目介绍

CrisisAgent 是一个面向企业危机回应的可审计多 Agent 原型。外层固定经过 Sentiment、Writer V1、RedTeam、Legal、Writer V2 和 Decision；我重点深化 Legal，让它围绕 Claim 在有限预算内执行 Action、接收 Observation 并重新判断。系统生成的是待审核草稿，不是自动发布。

## 1 分钟项目介绍

CrisisAgent 解决的是“事实不完整、法律依据待查时，如何安全地产生可审查的危机回应”。**固定的是高风险审核流程，不是模型输出。** Legal 先由程序计算 eligible actions；有多个有意义选项时，Legal LLM 才提议动作，再由 Program Validator 校验。**模型拥有提议权，程序拥有执行权。**

企业事实缺口进入 Human Fact，法律规则缺口进入 Legal RAG；人工回复作为 Observation 恢复同一次 Legal Task，并保留 Claim Progress 与预算。`FACT_PROVIDED` 仍是 `human_asserted`，不是独立核验事实。系统最终生成待审核草稿，不能自动发布。

## 3 分钟项目介绍

这个项目的核心思路是：危机回应不是一次 LLM 文案生成，而是一条固定的高风险审核流程。Sentiment、Writer V1、RedTeam、Legal、Writer V2 和 Decision 各自承担固定步骤，必要时由 Human Review 接手。固定的是审核顺序，不是每一步的模型输出。

Legal 是我重点做深的阶段。它先抽取 Claim 并识别每个 Claim 需要企业事实还是法律规则依据，再由程序计算当前 eligible actions。只有多个有意义选项时才调用 Legal LLM 提议；Program Validator 检查白名单、目标 Claim 和预算，通过后程序才执行。动作结果形成 Observation，更新 Claim Progress 后重新计算下一步；达到停止条件或预算上限后进入既有安全审核路径。

Human Fact 和 Legal RAG 处理不同问题：前者补充企业个案事实，后者检索法律规则候选材料，RAG 不能证明企业事实。人工回复会作为新 Observation 恢复同一 Legal Loop，不会重跑整个 Workflow；`FACT_PROVIDED` 仍是 `human_asserted`，需要保守处理。

一次 food-01 Bad Case 暴露了 Human Fact 不可得时任务过早停止、后续 Claim 未继续处理的问题。补上 Claim progression 与受限恢复后，food-01 的一次 Real Provider Trigger Replay 观察到多个 Claim 依次处理，并在预算耗尽后进入 Final Review。该次 Claim Extraction Provider 调用和结构化解析成功，但单次运行不是严格 A/B；它证明有界多 Claim continuation 在该次真实运行中发生，不证明通用自主规划、Proposal 优于 deterministic baseline 或 Claim Extraction 全面语义正确。

最近一次完整离线回归（2026-10-03）为 `1078 passed, 1 skipped`，这是工程回归证据，不是 Agent 语义质量指标。项目仍是 engineering prototype：尚未完整生产部署，也未完成外部真实用户验证。

## 面试官可能追问

### 1. 为什么不用 LangGraph 或现成 Agent 框架？

背诵版回答：这个项目主要是为了展示我对 Agent Runtime 的理解，所以我自己实现了 Planner、Validator、Executor、AgentState 和 Checkpoint。这样我能清楚解释状态怎么流转、Agent 结果怎么传递、Human Gate 怎么暂停和恢复。如果在真实团队里需要更复杂编排，我也可以把这些概念迁移到 LangGraph 等框架上。

### 2. Dynamic Runtime 和 Fixed Workflow 有什么区别？

背诵版回答：外层六步 Workflow 固定，避免高风险审核步骤被跳过；Legal 内部则允许有限的任务推进。程序先算 eligible actions，必要时让 Legal LLM 提议，再由 Validator 决定提议是否可执行。Observation 更新 Claim Progress 后会重新计算动作，Checkpoint 支持 Human Fact 后恢复同一次 Legal Task。

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

### 5.1.1 改了 RAG 后怎么防止退化？

背诵版回答：我给 Legal RAG 做了固定评测集和 baseline regression。`data/rag_retrieval_eval_cases.json` 覆盖 food_safety、data_privacy、service_outage、false_advertising、labor_dispute、product_recall、financial_rumor、executive_scandal 等类别，`reports/rag_baseline.json` 保存当前基线。每次改知识库、query rewrite、chunk、rerank 或 retriever 后，运行 `scripts/run_rag_regression.py`，对比 top3 source hit rate、fallback rate 和 context pollution rate。如果明显低于基线就返回失败。这个评估不调用真实 LLM，也不会把小型自建评测集夸成公开 benchmark。

### 5.2 RAG 证据质量差时怎么办？

背诵版回答：我不会把“检索到了内容”直接等同于“证据可靠”。项目新增了 RAG Evidence Quality Gate，它只读取 Legal Agent 已有的 `evidence_chunks` metadata，不重排、不重新检索。如果 evidence 为空、fallback_used=true、score/rerank_score 低、source_category 不匹配或 context pollution rate 过高，就标记 `low_confidence=true`，并建议进入 Human Review。这样 Legal Agent 可以继续生成审查建议，但 trace 会明确告诉审核人：这次 RAG evidence 置信度不足，不能盲目依赖。

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

### 11. 从固定 workflow 到可控 Tool-Using Agent 怎么做？

背诵版回答：我没有把系统改成完全自主 Agent，因为危机公关是高风险场景，不能让模型自由跳过 Legal、Guardrail 或 Human Review。我做的是可控 Tool-Using Legal Agent 实验：先根据 event、sentiment、redteam 生成结构化 tool plan，再通过 Function Calling Adapter 执行 `legal_rag_search`、`guardrail_check`、`knowledge_document_search` 等 skill，最后把 observation 汇总成 legal_risks、safe_points 和 revision_advice。高风险 plan 必须包含 Legal RAG 和 Guardrail，approve/reject/publish 这类敏感动作被 tool policy 禁止由 LLM 自主调用。

### 12. fast / standard / strict 推理模式怎么设计？

背诵版回答：我没有直接重写 workflow，而是先做了一个 reasoning mode selector。它根据 risk_level、guardrail_triggered、RAG evidence 数量和置信度、LLM fallback、用户是否要求严格审核来选择 fast、standard 或 strict。fast 用于低风险轻量处理；standard 走正常多 Agent 流程；strict 用于高风险或不稳定输出，建议强制 Legal RAG、Guardrail 和 Human Review。当前它作为 AgentState metadata 和 API 返回中的 planning hint，不破坏原来的 `/api/dynamic/run`。

### 13. 多轮 follow-up 怎么利用 session state？

背诵版回答：我新增了 `/api/dynamic/{session_id}/followup`，它不是重新跑一遍 Agent，而是读取已有 session 的 original event、final_statement、scores、agent_trace、RAG evidence 和 guardrail metadata，生成 clarification、rewrite、media_qna、internal_action、regulator_response 这几类 mock follow-up。这样可以解释多轮对话不是无状态聊天，而是基于同一个 crisis session 的上下文继续处理。

### 14. 长文本生成为什么不直接一次性生成？

背诵版回答：长文本我会拆成 outline、分段生成、consistency check、final merge、guardrail、human review。特别是危机声明这种高风险文本，不能一边 streaming 一边直接给最终稿，因为后面可能出现法律措辞或事实定性问题。SSE 更适合展示进度，不应该替代最终审核。

### 15. Prompt 工程你是怎么做的？

背诵版回答：我把 Prompt 拆成 Role、Task、Context、Constraints、Output Schema 和 Examples。不同 Agent 的重点不同：Sentiment 看风险和情绪，Writer 看共情和公众表达，RedTeam 做攻击性审查，Legal 保守处理 RAG evidence 和法律风险，Decision 综合评分和最终声明。所有真实 LLM 路径都要求 JSON structured output，解析失败会进入 JSON repair 或 fallback trace。

### 16. 你这个项目是不是 AI 写的？

背诵版回答：我用了 AI 辅助开发，但不是让 AI 自由发挥。项目选题、Agent 拆分、技术路线、阶段验收、禁止修改范围、测试结果判断和 git diff review 都是人主导。AI 主要加速样板代码、测试、文档和重复性改造。每个阶段我都会明确“不要改 Agent 业务逻辑、Prompt 主语义、RAG 算法和 API”，最后用 pytest 和 diff 检查质量。

### 17. 什么是代码知识库 Agent？你这个项目做到了吗？

背诵版回答：代码知识库 Agent 的核心是把代码文件、模块职责、类函数和错误信息关联起来，帮助定位跨模块问题。我现在做的是轻量静态索引：`scripts/index_project_knowledge.py` 扫描 core、rag、agents、skills，输出 `data/code_knowledge_index.json`。它可以辅助解释 RAG evidence 丢字段、RQ worker 失败、pgvector fallback、guardrail 未触发这类跨模块问题。但我会明确说明它还不是完整代码 Agent，没有 semantic code search、自动 patch 或自主执行工具链。

### 18. 你怎么验证项目不是只跑通一个 demo？

背诵版回答：最近一次完整离线回归（2026-10-03）是 1078 passed、1 skipped，说明工程回归通过，不等于 Agent 语义质量。Real Provider 证据目前是 food-01 一次 bounded multi-Claim Trigger Replay，不是 benchmark；外部真实用户验证尚未完成。我会把自动化测试、冻结集、真实模型运行和 User 0 内部浏览器 E2E 分开描述。

### 19. 这个项目最大的不足是什么？

背诵版回答：第一，async 默认仍是 in-process，Redis + RQ 是可选增强但还没有 dead-letter queue；第二，pgvector 只是可选 backend，还没有做 ANN 对照和生产压测；第三，Reranker 是手写规则；第四，真实 LLM 输出仍有结构化不稳定，需要更强的 retry-with-format 或 provider response_format；第五，module-level RAG trace state 仍需继续收敛。
