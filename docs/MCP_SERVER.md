# CrisisAgent MCP Server

## 定位

CrisisAgent 的 MCP 层是工具协议适配层，不重写 Agent Workflow、Legal Agent 或 RAG。第一阶段通过 MCP 暴露少量安全、只读能力，让外部 Agent 可以用标准工具协议调用现有能力。

当前代码状态：

```text
MCP Client / Inspector
    -> MCP Server
    -> MCP safety allowlist
    -> ToolRunner
    -> SkillRegistry / ToolDefinition
    -> existing handler
```

## 第一阶段工具

默认只暴露：

- `legal_rag_search`
- `guardrail_check`
- `runtime_metrics_query`
- `knowledge_document_search`

`knowledge_document_search` 会强制使用已发布且启用的知识文档。MCP 不允许开启 live-fetch，也不允许修改知识库。

不暴露：

`approve`、`reject`、`publish`、`final_publish`、`send_notification`、`delete_session`、`modify_knowledge_base`、`live_fetch` 和 workflow 执行工具。

## ToolRunner 关系

MCP 不直接调用 `SkillRegistry.execute()`，而是调用 `ToolRunner.run()`。因此参数校验、输出校验、timeout、bounded retry、fallback、execution budget、loop detection、`error_code`、`human_review_required` 和 trace 都沿用现有工具层能力。

MCP transport 成功不代表工具业务成功。Server 能够正常响应时，`mcp.protocol_status` 为 `success`；具体工具失败放在 `tool_result.error_code` 中。MCP 连接失败、工具执行失败和 RAG retrieval failure 是三个不同层级。

## Transport 路线

stdio 是第一阶段的本地协议验证 transport，适合 MCP Inspector 和离线测试。stdout 只保留协议内容，启动提示写入 stderr。

项目最终目标是支持联网使用，但当前还不能宣称是生产级远程 MCP 服务。后续 streamable HTTP 版本必须补充：

- JWT 或 API key；
- MCP tool authorization；
- CORS；
- rate limit；
- request body size limit；
- audit log；
- session permission；
- health/readiness；
- HTTPS。

即使扩展为 HTTP，live-fetch、approve、publish 和 send_notification 也不应默认开放给外部 Agent 自动调用。

## 运行

安装可选依赖：

```bash
python -m pip install -r requirements-mcp.txt
python -m backend.mcp.server
```

未安装 MCP SDK 时，核心 `backend.mcp.tools` 仍可在普通 pytest 中直接测试；只有真实协议 Server 需要可选依赖。

离线 demo：

```bash
python scripts/demo_crisis_mcp_tools.py
```

## 面试讲解版

我没有把整个 CrisisAgent 重构成 MCP 平台，而是把 MCP 放在工具协议层。内部已有 Skill Registry、ToolDefinition 和 ToolRunner，因此 MCP 只负责安全工具筛选、协议转换和结构化返回。第一阶段选 stdio 是为了先验证协议适配、ToolRunner、安全白名单和错误边界；后续要开放 streamable HTTP，还必须补齐鉴权、授权、限流、审计、HTTPS 和 session 权限。
