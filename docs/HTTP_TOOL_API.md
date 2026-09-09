# HTTP Tool API

## 定位

HTTP Tool API 将 CrisisAgent 已有的安全工具通过 REST 暴露给外部 AI Client 或企业系统。它不是开放任意函数执行的接口，也不替代 CrisisAgent 的 Agent Workflow。

```text
HTTP Client
  -> /api/tools safety allowlist + RBAC
  -> MCP Safe Adapter
  -> ToolRunner
  -> ToolDefinition / SkillRegistry
  -> existing read-only handler
```

所有实际执行都会复用 `ToolRunner`，因此输入输出 schema 校验、timeout、bounded retry、fallback、execution budget、loop detection、结构化 `error_code` 与 trace 保持一致。

## 安全工具

第一版仅允许：

- `legal_rag_search`
- `guardrail_check`
- `runtime_metrics_query`
- `knowledge_document_search`

第一版明确禁止：

- `approve`、`reject`
- `publish`、`final_publish`
- `send_notification`
- `delete_session`
- `modify_knowledge_base`
- `live_fetch`
- `run_crisis_workflow`、`run_crisis_workflow_mock`

allowlist 在后端 `backend/mcp/schemas.py` 定义，不能通过隐藏前端按钮绕过。`knowledge_document_search` 仍然只检索已发布、启用的知识文档。

## API

### `GET /api/tools`

返回当前安全 allowlist 中的工具定义，包括输入输出 schema、风险等级、只读属性和版本。

### `POST /api/tools/run`

```json
{
  "tool_name": "guardrail_check",
  "arguments": {
    "statement": "我们保证绝不会有任何问题。"
  },
  "request_id": "external-request-001",
  "session_id": "optional-session-id",
  "dry_run": false
}
```

响应包含 `tool_run_id`、结构化输出、`error_code`、`human_review_required`、ToolRunner trace 和起止时间。`dry_run=true` 只校验工具选择和授权，不执行 handler。

## 权限与审计

- `admin`、`operator`：可查看并运行全部安全工具。
- `legal_reviewer`：可查看工具，仅能运行 `legal_rag_search` 与 `guardrail_check`。
- `viewer`：仅能查看工具列表。

`AUTH_ENABLED=false` 下保留 Workbench 的演示角色 header；`AUTH_ENABLED=true` 下复用项目 JWT。接口会记录 `tool.list`、`tool.run`、`tool.run.denied` 和 `tool.run.failed` 审计事件，包含工具名、request/session ID、错误码和人工审核标记。

## 当前边界

- REST API 不是 Streamable HTTP MCP transport。
- 不提供 API key、rate limit、请求体大小限制或多租户隔离；这些是远程企业集成的后续工作。
- 工具接口不启用真实 live-fetch，不调用 Workflow，也不自动发布内容。
- 普通 pytest 使用离线 handler / fake 结果，不访问真实网络或真实 LLM。

## 面试讲解版

我没有为了支持外部 Agent 就开放一个任意工具执行接口，而是把已有 MCP Safe Adapter 和 ToolRunner 包在 HTTP 层外面。HTTP 层只处理认证、RBAC 和审计，真正执行仍通过同一个安全 allowlist 和 ToolRunner，因此参数校验、超时、重试、fallback 和执行预算不会因 transport 改变。第一版只开放法律检索、Guardrail、运行指标和已发布知识库查询，审批、发布、通知、实时采集和 workflow 执行全部在服务端拒绝。
