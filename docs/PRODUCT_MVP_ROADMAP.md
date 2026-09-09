# CrisisAgent Product MVP Roadmap

## 1. 当前项目定位

CrisisAgent 是一个 **live-news-driven, evidence-guided enterprise crisis response Copilot workbench**。它面向企业 PR、法务和品控团队，将受控新闻源、白名单来源或人工录入事件转为可分级、可审核、可追踪的响应草稿、法律风险意见和审计报告。

当前项目是具备工程化思路的 MVP / prototype，不是已经部署的生产级 SaaS。

当前边界：

- 不是全网实时爬虫平台；
- 不是自动发布声明系统；
- 不是 one-shot LLM demo；
- 不是已经接入企业生产数据的线上平台；
- 白名单 live-fetch 只用于受控验证，不默认开启；
- MCP Safe Adapter 当前优先服务本地协议验证，远程联网能力仍需补齐安全基础设施。
- GDELT DOC 与 NewsAPI 是手动启用的准实时新闻连接器，不代表全网实时监控覆盖。

## 2. 为什么当前还不够落地

P18 新增 Watchlist 驱动的准实时监测入口，用于围绕公司、品牌和产品生成受控查询、保存 Public Signals 并产生人工确认 Alert；它仍不是全网实时监控。
P18 同时增加离线 Monitoring Eval，用于观察 mention relevance、risk precision、duplicate rate、alert precision 和 bad case。
P19 增加 production-like demo、受控 GDELT live smoke 文档和 scheduled live monitoring 脚本，用于人工验收准实时链路。

现有 Agent 内核和安全边界已经比较完整，但从“可运行的 Agent 工程原型”到“企业可使用的产品”还缺少以下产品闭环：

- 缺少面向业务人员的数据源管理界面和 API；
- 缺少采集任务的创建、状态查询、失败重试和历史记录 API；
- 缺少持久化的危机事件库；
- 缺少事件列表、详情、来源和事件状态管理；
- 缺少趋势、风险分布、来源健康度等业务看板；
- 缺少面向企业审核流程的 Markdown/JSON 报告导出；
- 缺少远程 API/MCP 所需的更完整鉴权、授权、限流、审计和会话权限。

因此，下一阶段重点不是继续堆 Agent 或工具，而是把现有能力连接到可操作、可追踪、可复用的产品流程中。

## 3. 最小可落地产品闭环

目标闭环如下：

```text
企业人员打开系统
    -> 管理白名单舆情来源
    -> 手动触发采集
    -> 系统清洗、去重并生成事件 cluster
    -> 保存 CrisisEvent
    -> 查看来源、风险等级、fact_status、event_status
    -> 选择事件运行 CrisisAgent
    -> 查看 Agent Trace 和 Human Review
    -> 导出危机处理报告
```

这里的“采集”仍然是受控采集：系统只处理登记过的 RSS、单篇文章 URL，或手动启用的 GDELT DOC / NewsAPI 查询连接器；不通过递归爬取扩大范围，也不自动发布回应。

## 4. 可借鉴 DocReview-Agent-System 的部分

可以借鉴它在 Agent 工程化上的结构性做法：

- MCP stdio / HTTP 双模式；
- `health`、`tools`、`invoke` 等清晰的服务入口；
- 执行前门控；
- checkpoint/resume；
- 停滞检测；
- 成本和执行预算控制。

这些能力可以帮助 CrisisAgent 把工具执行和远程调用做得更可控，但不应照搬文档评审业务。CrisisAgent 的核心对象仍然是舆情来源、危机事件、Agent trace、证据和人工审核。

## 5. 可借鉴 campus-opinion-analysis 的部分

可以借鉴其产品化方向：

- 数据采集模块；
- 增量去重；
- 数据入库；
- FastAPI 后端接口；
- Vue3 + ECharts 可视化大屏；
- 趋势分析和热点检测；
- 风险指数；
- 报告导出；
- Docker Compose 本地运行方案。

但不照搬登录论坛 Token 爬虫或其他需要授权的采集方式，不采集个人隐私，也不把“能抓取数据”当作系统已经具备企业生产数据能力。

## 6. 后续实施路线

### P1：Source Registry API

P1 已新增 Source Registry API，用于通过后端管理白名单舆情源；它只管理配置，不默认触发 live-fetch。

把现有白名单 Source Registry 从文件配置逐步扩展为可管理资源：

```text
GET   /api/sources
POST  /api/sources
PATCH /api/sources/{source_id}
POST  /api/sources/{source_id}/test
```

需要保留的约束包括 HTTPS、source type 白名单、robots、timeout、rate limit、max_items 和默认 disabled。

### P2：Ingestion Run API

P2 已新增 Ingestion Run API，用于通过后端手动触发采集/归并并保存 run 记录。

为采集任务提供可追踪的运行记录：

```text
POST /api/ingestion/run
GET  /api/ingestion/runs
GET  /api/ingestion/runs/{run_id}
```

运行记录至少应区分：`collected`、`no_match`、`failed`、`skipped_by_robots` 和 `disabled`，不能把采集失败误判成没有舆情。

### P3：CrisisEvent 事件库

P3 已新增 CrisisEvent 事件库，用于把采集 run 中的 cluster 提升为可管理的危机事件。

将 `ClusteredCrisisEvent` 变成可以查询和关联 Agent 运行的业务对象：

```text
GET  /api/events
GET  /api/events/{event_id}
POST /api/events/{event_id}/run
GET  /api/events/{event_id}/trace
```

事件详情应保留来源、source_count、event_fingerprint、risk_level、fact_status、event_status、human_review_required 和关联的 Agent session。

### P4：事件运行 CrisisAgent + Trace / Human Review

P4 已新增事件运行 CrisisAgent、Trace 查询和 Human Review 状态查询能力。

事件入口复用现有 Dynamic Runtime，不改变 `/api/dynamic/run` 的请求语义：

```text
CrisisEvent
    -> Dynamic Runtime
    -> AgentState.metadata["ingestion"]
    -> Agent Trace / Human Review
```

### P5：Report 导出

P5 已新增事件报告导出能力，支持从已有 AgentRun 生成 Markdown / JSON 危机处理报告。

```text
GET /api/events/{event_id}/report
```

第一版支持 Markdown 和 JSON。报告应包含事件摘要、来源、风险、RAG evidence、Agent trace、Human Review 状态和最终决策，不应自动发布声明。

### P6：前端工作台

P6 新增前端工作台，用于串联来源管理、采集运行、事件库、Agent Run、Trace/Review 和 Report。

建议按业务任务拆分页面：

- 数据源管理页；
- 采集任务页；
- 危机事件列表页；
- 事件详情页；
- Agent Trace / Human Review 页；
- 报告页；
- 风险分布、24 小时趋势和来源状态统计。

### P7：手动联网采集入口

P7 新增手动联网采集入口，通过 `ENABLE_API_LIVE_FETCH`、用户确认、白名单 source、robots、timeout、rate limit 和 max_items 控制真实采集风险。

### P8：Crisis Radar Dashboard

P8 新增 Crisis Radar Dashboard，用于展示事件紧急程度、风险分布、待审核队列和来源健康状态。第一版基于既有事件和采集记录进行可解释规则聚合，不重新运行 Agent 或自动发布声明。

### P9：Eval Center

P9 新增 Eval Center，用于对 ingestion、event、urgency、agent_run、report 和 tool reliability 做离线评估，并支持 EvalRun、overview 和 regression 对比。

### P10：HTTP MCP / REST Tool API

在 stdio MCP 验证稳定后，再考虑联网服务化：

```text
GET  /health
GET  /tools
POST /api/tools/run
POST /mcp
```

远程版本必须补充 API Key 或 JWT、工具授权、CORS、rate limit、request size limit、audit log 和 session permission。HTTP MCP 不应直接获得审批、发布、通知或知识库修改权限。

### P11：Eval CI Gate / Golden Cases

P11 将 Eval Center 接入命令行和离线 CI 回归验证。虚构 Golden Cases 固化高风险、冲突事实和历史新闻等安全预期；CI 通过最低通过率和新增失败项检查，防止 Agent、RAG、Tool 或 Report 的工程改动造成已知质量契约退化。

### P12：Workspace Security & Audit

P12 为 Source、IngestionRun、CrisisEvent、AgentRun、Report 和 Eval 增加最小角色权限、owner 字段和 JSON 审计日志；认证开启时复用 JWT，关闭时保留 demo 角色模拟。该阶段已包含 JWT 产品 API 权限矩阵测试与 admin Audit Log 工作台查看区域。

### P13：Durable Data Foundation

P13 新增 Repository 抽象，默认保留 JSON demo storage，并为 Source、IngestionRun、CrisisEvent、AgentRun、EvalRun、AuditLog 定义可选 PostgreSQL 持久化基础与 JSON 导出迁移包。

## 7. 真实采集边界

第一版真实采集只允许：

- 白名单 RSS 或单篇 `article_url`，以及手动启用的 GDELT DOC / NewsAPI 查询连接器；
- HTTPS URL；
- 遵守 `robots.txt`；
- 明确的 timeout；
- 明确的 rate limit；
- 明确的 `max_items`；
- 手动显式开启 live-fetch。

明确禁止：

- 全网递归爬取；
- 绕过登录或权限控制；
- 绕过验证码或反爬机制；
- 使用代理池绕过限制；
- 采集个人隐私；
- 采集需要授权的内容；
- 通过 MCP 默认开启 live-fetch；
- 自动发布声明。

采集结果必须先经过 normalize、deduplicate、cluster 和 risk analyze。高风险、未证实、事实冲突或事件状态不确定时，继续进入 Human Review。

## 8. 面试讲解版

### 1 分钟版

> CrisisAgent 目前不是单纯的聊天机器人，而是一个企业舆情危机响应 Agent 原型。Agent 内核已经包含舆情 ingestion、事件归并、风险分析、固定 Workflow、Dynamic Runtime、Legal RAG、Guardrail、Human Review、Checkpoint/Resume、ToolRunner 和 MCP 安全适配。为了让它真正落地，下一步不是继续增加 Agent 数量，而是补产品闭环：数据源管理、采集任务、危机事件库、事件详情、报告导出和前端工作台。真实采集也不会做成全网乱爬，而是采用白名单 RSS/单篇文章，或手动启用的 GDELT DOC / NewsAPI 查询连接器，并保留 robots、限速、超时和人工审核边界。这样系统先保证来源可控、事件可追踪、结果可审计，再逐步扩展联网服务能力。

### 30 秒版

> 我把 CrisisAgent 分成 Agent 内核和产品入口两部分。当前已经完成了 ingestion、事件归并、RAG、Guardrail、Human Review、ToolRunner 和 MCP 安全适配；还没有把它包装成已上线的实时监控 SaaS。下一步会补 Source Registry、采集任务、CrisisEvent 事件库、事件详情和报告导出。真实采集只做白名单、低频、可审计入口，不做全网爬虫和自动发布。

### STAR 版

**Situation：** 原型已经能对一条事件输入执行多 Agent 危机响应，但企业人员还缺少来源管理、事件沉淀和结果导出的完整入口。

**Task：** 在不破坏现有 Agent 主链路的前提下，把工程原型推进成可以实际操作的最小产品闭环。

**Action：** 先复用现有 ingestion、metadata bridge、Human Review、ToolRunner 和 MCP 安全白名单，再按 Source Registry、Ingestion Run、CrisisEvent、Report 和前端工作台分阶段建设。采集侧坚持白名单 RSS/文章 URL、robots、限速、超时和默认关闭 live-fetch。

**Result：** 当前已经具备受控采集和 Agent 内核验证能力，下一阶段将重点补事件库、任务状态、报告和远程安全能力。项目可以诚实地称为具备生产化思路的工程原型，而不是已经上线的生产级 SaaS。

## 9. 路线判断

最优先的下一步不是引入更多框架，而是完成以下最小链路：

```text
Source Registry
    -> Ingestion Run
    -> CrisisEvent
    -> Agent Run
    -> Human Review
    -> Report Export
```

这条链路完成后，企业用户才可以从系统中完成一次完整的“发现舆情、确认事件、运行分析、人工审核、导出结果”流程。
## P14: Redis-required Background Ingestion Jobs

P14 adds Redis-backed background ingestion dispatch and status polling. Redis
only carries queue jobs; IngestionRun repository storage remains the product
business-state source of truth.

## P15: Queue Reliability

P15 adds bounded retry, dead-letter state, timeout metadata, worker heartbeat,
and a safe stuck-ingestion recovery script without moving business data into Redis.

## P16: HTTP Tool API

P16 exposes the existing MCP Safe Adapter and ToolRunner through `GET /api/tools`
and `POST /api/tools/run`. Only the read-only safe allowlist is available, with
JWT/demo RBAC and audit records; workflow execution, live fetch, approval and
publishing actions remain blocked.

## P20: Case Memory And ContextPack

P20 adds reviewed case memory, deterministic memory retrieval, and bounded ContextPack previews. It does not change the existing Agent workflow, Prompt, or RAG algorithm; unreviewed external signals are not promoted into long-term memory.
