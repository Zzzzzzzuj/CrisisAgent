# CrisisAgent Demo Guide

本文档用于 GitHub 展示和面试演示。推荐目标是在 5 到 8 分钟内讲清楚：系统如何把一个危机事件拆成多 Agent 流程，如何进入 Human Review，如何保存 checkpoint，以及如何通过 Trace / Metrics 排查运行过程。

## 1. Backend

```powershell
cd C:\path\to\CrisisAgent
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:5173
```

演示路径：

1. 打开 Crisis Dashboard。
2. 新建危机案例。
3. 进入详情页查看风险等级、AI 声明、Human Review。
4. 展开高级分析查看 Agent Trace、RAG、Gate、Metrics、Raw JSON。

## 3. Mock Demo

Mock 模式适合离线演示和普通测试：

```powershell
$env:AGENT_MODE="mock"
$env:CHECKPOINT_STORAGE="json"
$env:RUNTIME_MODE="sync"
python scripts\run_demo_cases.py
```

脚本会输出：

- case 名称
- plan
- dynamic runtime 结果
- agent trace
- RAG 命中
- memory 命中
- evaluation
- human gate 状态
- final statement

## 4. Recommended Demo Route

推荐给 GitHub 访问者或面试官的演示路线：

### Demo 模式 A：完全离线 mock demo

适合面试现场、GitHub 快速复现和无数据库环境：

- `AGENT_MODE=mock`
- `CHECKPOINT_STORAGE=json`
- `RUNTIME_MODE=sync`
- 不消耗真实 LLM
- 不依赖 PostgreSQL

### Demo 1：Mock 完整流程

```powershell
$env:AGENT_MODE="mock"
$env:CHECKPOINT_STORAGE="json"
$env:RUNTIME_MODE="sync"
python -m uvicorn backend.main:app --reload
```

另开一个 PowerShell 运行：

```powershell
$env:AGENT_MODE="mock"
$env:CHECKPOINT_STORAGE="json"
$env:RUNTIME_MODE="sync"
python scripts\run_full_demo.py
```

`run_full_demo.py` 会依次检查：

- backend health check
- readiness check
- runtime metrics check
- mock dynamic workflow demo
- RAG evidence demo
- RAG ablation demo

注意：`backend/db/session.py` 会读取 `backend/.env`。如果本机 `backend/.env` 里配置了 `CHECKPOINT_STORAGE=postgres`，但当前环境没有安装 `psycopg` 或数据库未启动，`/ready` 和 runtime metrics 会失败。离线 mock demo 推荐使用 `CHECKPOINT_STORAGE=json`。

如果后端没有启动，脚本会提示：

```text
Start backend first: python -m uvicorn backend.main:app --reload
```

### Demo 2：RAG Evidence

在 Dashboard 的 Case Detail 页面展开高级分析，查看 Legal Agent Trace：

- `rag_used`
- `retrieval_backend`
- `retrieval_query`
- `evidence_chunks`
- `score`
- `rerank_score`
- `evidence_summary`

### Demo 3：RAG Ablation

```powershell
python scripts\run_rag_ablation_demo.py
```

重点看：

- `RAG_ENABLED=false` 时 `rag_used=false`、`evidence_chunks_count=0`。
- `RAG_ENABLED=true` 时 `rag_used=true`、`evidence_chunks_count>0`。
- 食品安全示例会命中 `food_safety.md`。

### Demo 4：Async Runtime

```powershell
$env:RUNTIME_MODE="async"
$env:TASK_QUEUE_BACKEND="inprocess"
python -m uvicorn backend.main:app --reload
```

创建 dynamic case 后，`POST /api/dynamic/run` 会快速返回 `queued`，再通过 `GET /api/dynamic/{session_id}` 查询状态变化。

可选 Redis + RQ durable queue：

```powershell
docker compose up -d redis
$env:RUNTIME_MODE="async"
$env:TASK_QUEUE_BACKEND="rq"
$env:REDIS_URL="redis://localhost:6379/0"
$env:RQ_QUEUE_NAME="crisisagent"
python scripts\run_rq_worker.py
```

另开一个 PowerShell 启动 backend：

```powershell
$env:RUNTIME_MODE="async"
$env:TASK_QUEUE_BACKEND="rq"
$env:REDIS_URL="redis://localhost:6379/0"
python -m uvicorn backend.main:app --reload
```

`inprocess` 适合离线 demo，不需要 Redis；`rq` 适合更接近生产的长任务执行，任务进入 Redis/RQ，由独立 worker 消费。

### Demo 5：Auth / RBAC Review

```powershell
$env:AUTH_ENABLED="true"
$env:SECRET_KEY="<strong-random-secret>"
```

登录后使用 `legal_reviewer` 或 `admin` token 执行 approve/reject。`operator` 只能创建和查看 case，不能审核。

### Demo 6：Runtime Metrics / Ready Check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runtime
```

Dashboard 首页也会展示 runtime metrics 卡片；如果 metrics API 暂不可用，不影响 case list 展示。

### Demo 模式 B：PostgreSQL demo

适合展示 checkpoint、trace、approval 和 audit log 落库：

```powershell
pip install -r requirements.txt
$env:CHECKPOINT_STORAGE="postgres"
$env:DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5432/crisis_agent"
python -m alembic upgrade head
python -m uvicorn backend.main:app --reload
```

PostgreSQL demo 必须满足：

- `requirements.txt` 中的 `psycopg[binary]` 已安装到当前虚拟环境。
- `DATABASE_URL` 指向可连接数据库。
- Alembic migration 已执行：`python -m alembic upgrade head`。
- 如果 `/ready` 显示 `ModuleNotFoundError` 或 `postgres` backend 不可用，先检查依赖和数据库；若只是演示 Agent/RAG，可以切回 `CHECKPOINT_STORAGE=json`。

## 5. Real LLM Demo

真实 LLM demo 需要配置 OpenAI-compatible API，例如 DeepSeek：

```powershell
$env:AGENT_MODE="llm"
$env:LLM_PROVIDER="openai_compatible"
$env:LLM_MODEL="<model-name>"
$env:LLM_BASE_URL="<provider-base-url>"
$env:LLM_API_KEY="<your-api-key>"
python scripts\run_real_llm_demo.py
```

不要把真实 API Key 写进命令历史截图、README、报告或 Git。

真实 smoke 可能出现 LLM structured output 不稳定，系统会通过 JSON parsing、字段校验和 fallback 保持链路继续运行。面试中应明确区分“真实 LLM 请求成功”和“触发 mock fallback 后流程成功”。

## 6. 如何验证 RAG 真的生效

RAG 展示不要只看最终声明是否更像样，而要看 Legal Agent trace 里的 evidence 是否真的进入了审核过程。

运行 RAG ablation demo：

```powershell
python scripts\run_rag_ablation_demo.py
```

观察输出中的两组结果：

- `RAG_ENABLED=false`：`rag_used=false`，`retrieval_backend=none`，`evidence_chunks_count=0`。
- `RAG_ENABLED=true`：`rag_used=true`，`retrieval_backend=markdown` 或 `db`，`evidence_chunks_count>0`。
- 示例食品安全 case 会命中 `food_safety.md`，并展示 Legal Agent 使用了 3 个 evidence chunks。

在 Dashboard 里验证：

1. 新建一个食品安全、数据隐私或产品质量危机 case。
2. 进入 case detail。
3. 展开“高级分析”。
4. 查看 Legal Agent 的 RAG / Gate trace。
5. 重点确认 `rag_used`、`retrieval_backend`、`retrieval_query`、`evidence_chunks`、`score`、`rerank_score` 和 `evidence_summary`。

面试演示时可以这样讲：

```text
我不是只看最终回答来证明 RAG 有用，而是看 trace 中 Legal Agent 是否实际拿到了 evidence chunks，
并通过 RAG_ENABLED=false/true 对同一个 case 做 ablation，对比 legal_risks、safe_points、final_statement、
guardrail 和 evaluation score。
```

## 7. Async Runtime

切换异步模式：

```powershell
$env:RUNTIME_MODE="async"
python -m uvicorn backend.main:app --reload
```

创建动态任务：

```powershell
$body = @{ event = "某食品品牌被曝光使用过期原料，消费者要求监管介入。" } | ConvertTo-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$result = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/dynamic/run `
  -Body $bytes `
  -ContentType "application/json; charset=utf-8"
$result.session_id
$result.status
```

异步模式下初始返回通常是 `queued`。随后查询：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/dynamic/$($result.session_id)"
```

注意：默认 worker 是 in-process worker pool；如果设置 `TASK_QUEUE_BACKEND=rq`，需要 Redis 和独立 RQ worker。

## 8. PostgreSQL Backend

使用 Docker Compose：

```powershell
docker compose up -d postgres
```

配置：

```powershell
$env:CHECKPOINT_STORAGE="postgres"
$env:DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5432/crisis_agent"
python -m alembic upgrade head
```

运行 demo：

```powershell
python scripts\run_demo_cases.py
```

查询 API：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/dynamic/sessions
```

PostgreSQL 路径用于证明 checkpoint、trace、approval 和 audit log 可以落库；普通 pytest 仍默认走 JSON fallback。

## 9. Auth Enabled

默认：

```powershell
$env:AUTH_ENABLED="false"
```

开启：

```powershell
$env:AUTH_ENABLED="true"
$env:SECRET_KEY="<strong-random-secret>"
```

登录：

```powershell
$loginBody = @{ username = "reviewer"; password = "<password>" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/auth/login `
  -Body $loginBody `
  -ContentType "application/json"
$token = $login.access_token
```

审核时携带 token：

```powershell
$headers = @{ Authorization = "Bearer $token" }
$approveBody = @{ comment = "同意发布，注意同步客服 FAQ。" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/dynamic/<session_id>/approve" `
  -Headers $headers `
  -Body $approveBody `
  -ContentType "application/json"
```

`operator` 不能 approve/reject；`legal_reviewer` 和 `admin` 可以。

## 10. Readiness and Metrics

Readiness：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Runtime metrics：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runtime
```

重点讲解字段：

- `total_sessions`
- `completed_sessions`
- `failed_sessions`
- `waiting_human_sessions`
- `llm_fallback_count`
- `guardrail_trigger_count`
- `rag_hit_count`
- `approval_count`
- `rejection_count`

## 11. Suggested Interview Demo Script

1. 用一句话说明项目：企业危机响应 Agent 平台，不是单 Prompt 生成公关稿。
2. 展示 Dynamic Runtime：Planner -> Validator -> Executor -> AgentState。
3. 展示 Legal Agent：Gate 决定是否需要 RAG，RAG trace 展示来源和 rerank score。
4. 展示 RAG Ablation：同一 case 下 `RAG_ENABLED=false/true` 的 evidence 差异。
5. 展示 Human Review：高风险 case 进入 WAITING_HUMAN，审核人 approve/reject 后有 audit log。
6. 展示生产化：PostgreSQL、Alembic、Auth/RBAC、Guardrails、Observability。
7. 展示诚实边界：默认 async 是 in-process，RQ 是可选增强；metrics 不是 Prometheus，embedding 不是 pgvector。
