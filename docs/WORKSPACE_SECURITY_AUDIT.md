# Workspace Security And Audit

P12 为产品 API 增加最小角色控制和 JSON 审计留档。角色包括 `admin`、`operator`、`legal_reviewer` 和 `viewer`：管理员管理来源与审计；operator 运行采集和事件 Agent；legal reviewer 查看 Trace、Review 和报告；viewer 仅查看工作台、事件和报告。

`AUTH_ENABLED=true` 时复用项目现有 JWT 用户上下文，缺少认证返回 401、角色不足返回 403。`AUTH_ENABLED=false` 时保持离线 demo 兼容，前端可用 `X-User-Id` 与 `X-User-Role` 模拟角色；该 Header 模式仅用于 demo，不是生产认证方案。

P12 的产品 API 测试使用 SQLite fixture 和真实登录 token 覆盖 admin、operator、legal reviewer、viewer 的 Source、Ingestion 与 Audit 权限矩阵。Workbench 也提供 admin 专属 Audit Log 区域；其他演示角色不会看到该列表。

`data/audit_logs.runtime.json` 保存动作、actor、资源、结果、原因和最小 metadata。第一版覆盖 source、ingestion、event、event agent、trace/review、report、dashboard 和 eval 的关键动作；管理员可通过 `GET /api/audit/logs` 查询。Source、IngestionRun、CrisisEvent、EventAgentRun 和 EvalRun 会保留 MVP 级 `created_by`、`updated_by` 或 `owner_id` 字段；旧 JSON 缺少这些字段时按空值兼容。

当前仍是 JSON-storage MVP。前端 Header 角色仅用于 `AUTH_ENABLED=false` 的演示；生产环境需要 JWT、OAuth 或企业 SSO，外加数据库审计、不可篡改日志、细粒度多租户 owner scope、限流与会话权限。

## 面试讲解

> 我把工作台从单人 demo 往团队试用推进时，没有只加一个登录页，而是先把操作角色、资源权限和审计事件落到 API 边界。认证开启时沿用 JWT，离线 demo 关闭认证时用 Header 仅模拟角色。来源管理、采集、事件运行、Trace、报告和 Eval 都有最小权限约束，拒绝操作也写 audit log。它不是企业 SSO 成品，但先保证谁能做什么、谁做过什么可追踪。
