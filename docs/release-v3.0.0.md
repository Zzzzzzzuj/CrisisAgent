# CrisisAgent v3.0.0 Release Notes

v3.0.0 是 CrisisAgent 从“多 Agent Demo”走向“production-ready prototype”的版本。这个版本重点不是增加新的 Agent 能力，而是补齐状态持久化、异步执行、权限审计、LLM 可靠性、RAG 知识管理和可观测性。

## 1. PostgreSQL Persistence

新增 PostgreSQL checkpoint backend，保留 JSON fallback。

核心表：

- `crisis_sessions`
- `agent_checkpoints`
- `agent_traces`
- `approvals`
- `evaluations`
- `audit_logs`

Checkpoint 统一通过 repository 接口访问：

- `save_checkpoint`
- `load_checkpoint`
- `list_checkpoints`
- `delete_checkpoint`

## 2. Alembic Migration

项目新增 Alembic migration，用于创建生产化状态表、用户表和知识库管理表。

运行：

```bash
python -m alembic upgrade head
```

## 3. Async Runtime

新增 `RUNTIME_MODE`：

- `sync`：保持旧行为，HTTP 请求等待完整 Agent 流程。
- `async`：`POST /api/dynamic/run` 创建 session、保存 checkpoint、提交后台任务并返回 queued。

已知限制：

- 当前 worker 是 in-process `ThreadPoolExecutor`。
- 默认不是 Redis/RQ/Celery；Phase 11 后 Redis + RQ 是可选增强路径。
- 进程重启可能丢失尚未执行的内存队列任务。

## 4. Auth / RBAC

新增最小认证和权限模型：

- `operator`
- `legal_reviewer`
- `admin`

新增 API：

- `POST /api/auth/login`
- `GET /api/auth/me`

`AUTH_ENABLED=false` 保持本地 demo 行为；`AUTH_ENABLED=true` 时 approve/reject 必须校验 JWT。

## 5. Real Reviewer Audit

Human Review 不再只能记录 demo reviewer 文本。开启 Auth 后，approve/reject 会记录：

- `reviewer_id`
- `reviewer_username`
- `reviewer_role`

审核动作同步写入 `audit_logs`。

## 6. LLM Reliability

LLMClient 增加：

- timeout
- retry
- exponential backoff
- failure type classification
- compact LLM trace

失败类型：

- `timeout`
- `rate_limit`
- `provider_error`
- `invalid_json`
- `schema_validation_failed`
- `empty_response`

Parser 增加 JSON repair，修复失败后才 fallback。

## 7. Guardrails

新增输入和输出 Guardrail：

- Prompt injection 检测
- 绝对承诺检测
- 未核实事实定性检测
- 直接承认违法检测
- 隐私信息泄露检测
- 跳过人工审核暗示检测

Guardrail 命中不会修改 Agent 输出，而是进入 Human Review。

## 8. RAG Knowledge Management

新增知识库管理能力：

- `knowledge_documents`
- `knowledge_chunks`
- document version
- embedding status
- published status
- chunk metadata

新增脚本：

- `scripts/ingest_knowledge_base.py`
- `scripts/list_knowledge_documents.py`

本地 Markdown fallback 仍保留。默认 embedding 存储是 JSON/list；pgvector 是后续可选生产化路径，不是默认 demo 依赖。

## 9. Observability / Metrics / Readiness

新增：

- `backend/observability/logger.py`
- `backend/observability/metrics.py`
- `backend/observability/readiness.py`

API：

- `GET /health`
- `GET /ready`
- `GET /api/metrics/runtime`

Runtime metrics 覆盖：

- session 状态
- Agent failure
- LLM call/fallback
- Guardrail trigger
- RAG hit/fallback
- approval/rejection
- average runtime latency

这不是 Prometheus 或 OpenTelemetry，只是项目内轻量 metrics collector。

## 10. Validation Status

当前测试结果：

```text
447 passed
```

Real DeepSeek + BGE minimal smoke：

```text
PASS_WITH_LLM_FALLBACK_OBSERVED
```

含义：

- DeepSeek OpenAI-compatible client 能真实请求。
- BGE `BAAI/bge-small-zh` 能真实运行。
- Dynamic Runtime 能完成真实端到端请求。
- 观察到部分 Agent structured output 不稳定并触发 mock fallback。

不能写成“所有 Agent 真实 LLM 稳定成功”。

## 11. Release Boundaries

v3.0.0 不包含：

- 分布式任务队列
- pgvector / ANN
- Prometheus / OpenTelemetry
- Cross Encoder reranker
- 模型微调
- 线上生产 SLA

更准确的表述是：

> CrisisAgent v3.0.0 是一个覆盖多 Agent Runtime、RAG、Human Review、Persistence、Auth、Guardrails 和 Observability 的 production-ready prototype。
