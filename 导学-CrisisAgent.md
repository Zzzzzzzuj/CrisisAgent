# CrisisAgent 项目导学大纲

## 项目用途与学习目标

CrisisAgent 是一个面向企业 PR、法务和品控团队的证据驱动危机响应 Copilot。它把舆情线索或人工事件整理成 `CrisisEvent`，经过固定的六步 Agent 流程生成可审核的声明草稿，并保留 Trace、Checkpoint、Human Review 和 Report。

本课程不把项目讲成“调用大模型写稿”，而是帮助学习者回答三件事：数据如何进入系统，Agent 如何在状态上协作，以及系统如何限制、恢复和评估高风险执行。

## 源码版本与本地改动

- 当前分支：`main`
- 当前提交：`2a1fa29`
- 工作区存在 P29 Agent Skills Runtime 的未提交改动，涉及 `SkillSelector`、运行时 Skills、ContextPack 和主流程旁路接入；学习时需区分已提交能力与工作区改动。

## 前置基础

- Python、FastAPI、Pydantic 基础
- Vue3 和 HTTP API 基础
- RAG 中的向量/关键词检索、重排和证据门控
- 状态机、Checkpoint、重试和幂等的基本概念

## 课程路线

### 第一课：项目全貌与最小请求链路

**读完能回答：** CrisisAgent 到底解决什么问题，一次事件如何变成声明草稿？

**主链：** 事件输入 → API → AgentState → 六步 Workflow → Human Review/完成 → Trace/Report。

**必读：** `backend/main.py`、`backend/workflow.py`、`backend/core/state.py`、`backend/agents/`。

**选读验证：** `frontend/src/pages/Workbench.vue`、`README.md`。

**暂缓：** ingestion 和 Harness 细节，分别在第三、七课展开。

**状态：** 大纲

### 第二课：固定 Workflow、Dynamic Runtime 与状态流转

**读完能回答：** 固定流程和动态运行时有什么区别，planner 是否可以任意改变 Agent 顺序？

**主链：** 请求 → 生成/校验计划 → Executor → Agent 注册表 → 状态更新 → Checkpoint/Resume。

**必读：** `backend/core/dynamic_runtime.py`、`backend/core/executor.py`、`backend/core/plan_validator.py`、`backend/core/checkpoint.py`。

**选读验证：** `tests/test_dynamic_runtime.py`、`tests/test_resume.py`。

**暂缓：** Skills 运行时接入，留到第七课。

**状态：** 大纲

### 第三课：舆情 Ingestion 到 CrisisEvent

**读完能回答：** 原始舆情来自哪里，为什么不能直接把新闻文本交给 Agent？

**主链：** JSON/CSV 或白名单 RSS → normalize → deduplicate → cluster → risk analyze → `ClusteredCrisisEvent` → Ingestion Run → `CrisisEvent`。

**必读：** `backend/ingestion/schemas.py`、`backend/ingestion/pipeline.py`、`backend/ingestion/source_adapters.py`、`backend/api/ingestion_routes.py`、`backend/api/event_routes.py`。

**选读验证：** `data/sentiment_ingestion_fixture.json`、`tests/test_sentiment_ingestion.py`、`docs/SENTIMENT_INGESTION.md`。

**边界：** live-fetch 仅允许白名单、显式开启、低频采集；默认不联网。

**状态：** 大纲

### 第四课：六类业务角色与 AgentState 协作

**读完能回答：** Sentiment、Writer、RedTeam、Legal、Writer V2、Decision 分别负责什么，数据怎样传递？

**主链：** Sentiment → Writer → RedTeam → Legal/RAG → Writer V2 → Decision。

**必读：** `backend/agents/sentiment_agent.py`、`backend/agents/writer_agent.py`、`backend/agents/redteam_agent.py`、`backend/agents/legal_agent.py`、`backend/agents/decision_agent.py`、`backend/core/state.py`。

**选读验证：** `backend/core/policy.py`、`tests/test_workflow.py`。

**重点：** 业务角色数量是六类；工作流步骤通常也对应这六步，但每步可能包含 ContextPack、Skill 和审核判断等辅助动作。

**状态：** 大纲

### 第五课：RAG、Evidence Gate 与 Human Review

**读完能回答：** 为什么不是所有事件都检索，什么情况下必须转人工？

**主链：** Retrieval Need Gate → 检索/重排 → Evidence Quality Gate → Legal 审查 → Review Policy → `WAITING_HUMAN` 或继续完成。

**必读：** `backend/rag/retrieval_need_gate.py`、`backend/rag/evidence_quality_gate.py`、`backend/agents/legal_agent.py`、`backend/core/policy.py`。

**选读验证：** `tests/rag/test_retrieval_need_gate.py`、`tests/rag/test_rag_evidence_quality_gate.py`、`tests/test_approval_scope.py`、`docs/` 下的 RAG 与 Human Review 文档。

**重点：** 旧批准只能覆盖已审核的 Trace 范围，不能自动豁免恢复后出现的新风险。

**状态：** 大纲

### 第六课：可观测性、存储与产品闭环

**读完能回答：** 为什么要保存 Run、Trace、Report 和事件，而不是只返回最终文本？

**主链：** Source/Run → CrisisEvent → AgentRun → Trace/Review → Markdown/JSON Report → Dashboard/Eval Center。

**必读：** `backend/api/event_run_routes.py`、`backend/api/report_routes.py`、`backend/api/dashboard_routes.py`、`backend/api/eval_routes.py`、`backend/api/audit_routes.py`。

**选读验证：** `backend/product_storage/`、`frontend/src/pages/Workbench.vue`、`docs/PRODUCT_MVP_ROADMAP.md`。

**重点：** 当前默认仍是本地 JSON/MVP 存储；不能表述为已经上线的生产 SaaS。

**状态：** 大纲

### 第七课：HarnessSpec、ContextPack 与受控 Skills

**读完能回答：** 一次 Run 使用了哪些运行策略，ContextPack 和 Skill 如何避免无差别注入？

**主链：** active Harness → 冻结 Runtime Context → 按角色构建 ContextPack → 规则化 Skill Selector → ToolRunner → State/Trace/Checkpoint。

**必读：** `backend/core/harness_runtime.py`、`backend/core/context_pack_runtime.py`、`backend/skills/skill_schema.py`、`backend/skills/tool_runner.py`。

**当前工作区改动：** `backend/skills/runtime_skills.py`、`backend/skills/skill_selector.py`、`backend/core/executor.py`、`backend/workflow.py` 等 P29 文件需单独对照 diff 阅读。

**选读验证：** `tests/test_harness_runtime_integration.py`、`tests/test_agent_skills_runtime.py`、`docs/P29_AGENT_SKILLS_RUNTIME.md`。

**重点：** 这是规则化、受授权范围限制的 Skills 执行，不是任意工具调用，也不是自动自优化。

**状态：** 大纲

### 第八课：可靠性、评测与受控迭代

**读完能回答：** 工具失败、循环、Bad Case 和 Harness 变更如何被发现、验证和回滚？

**主链：** ToolResult/Trace → Failure Diagnosis → Proposal → Candidate → Golden/Replay Evaluation → 人工审批 → Enable/Rollback。

**必读：** `backend/skills/execution_budget.py`、`evaluation/tool_reliability.py`、`evaluation/`、`backend/api/harness_routes.py`、`backend/api/proposal_routes.py`。

**选读验证：** `tests/test_tool_runner.py`、`tests/test_tool_execution_budget.py`、`tests/test_harness_iteration_e2e.py`、`docs/AGENT_RELIABILITY.md`。

**重点：** 评测结果只能作为人工决策依据；系统不自动修改 Prompt、不自动启用 Candidate、不自动发布。

**状态：** 大纲

## 尚未覆盖与需要核对的边界

- 真实企业数据、线上用户规模和生产 QPS：仓库没有足够证据确认。
- 真实 LLM、BGE、PostgreSQL、Redis 生产链路：离线测试不等于生产验证。
- P29 工作区改动是否最终提交：当前尚未提交。
- HTTP Tool API、MCP 和队列部署细节：建议在前八课后按面试追问单独展开。

## 学习提醒

若某个文件或原理看不懂，请继续追问 AI；本大纲先给学习路径，不替代逐行讲解。
