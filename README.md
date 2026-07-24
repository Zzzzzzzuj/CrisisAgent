# CrisisAgent

CrisisAgent 是一个基于多智能体架构的企业危机公关决策系统。它不是单纯的“生成一段公关稿”，而是把真实危机处理流程拆成可编排、可观测、可评测、可恢复的 Agent Runtime。

当前项目覆盖了从固定多 Agent workflow 到 Dynamic Agent Runtime 的完整演进：包括 Planner、Executor、AgentState、RAG、Memory、Tool Calling、Context Engineering、Evaluation、Human Gate、Checkpoint Resume，以及 Vue Dashboard。

## 技术架构

```text
User Event
  ↓
Planner
  ↓
Plan Validator
  ↓
Executor
  ↓
AgentState
  ↓
Agents
  ↓
RAG / Memory / Tools
  ↓
Evaluation
  ↓
Human Gate
  ↓
Checkpoint
  ↓
Resume
```

技术栈：

- Backend: Python, FastAPI, Pydantic, pytest
- Agent Runtime: Planner, Plan Validator, Executor, AgentState, Adapter, Human Gate, Checkpoint Resume
- LLM Infrastructure: OpenAI-compatible HTTP client, Prompt Loader, JSON Parser, mock/llm dual mode
- RAG: Markdown knowledge base, keyword retrieval, vector retrieval, hybrid retrieval, rule-based reranker
- Memory: Local JSON memory storage, memory retrieval, session-to-memory extraction
- Evaluation: workflow evaluation, RAG evaluation, memory evaluation, response evaluation, optional LLM-as-Judge
- Frontend: Vue3, Vite, Axios

## 核心能力

- Dynamic Agent Runtime: 根据事件动态生成执行计划，并由 Executor 按计划运行 Agent。
- Multi Agent Collaboration: 将舆情分析、文案生成、红队攻击、合规审查、最终决策拆成独立 Agent。
- Hybrid RAG: Agent B 合规审查可检索本地法规与危机回应知识库。
- Memory System: 支持从历史 session 中抽取企业危机经验，并供 Writer Agent 参考。
- Tool Calling: 提供统一 Tool 抽象，并让 Agent A 在 LLM 模式下使用舆情分析工具。
- Context Engineering: Writer Agent 使用 ContextManager 控制 event、sentiment、memory 等上下文。
- Evaluation System: 离线评估风险识别、情绪识别、RAG 召回、Memory 检索和最终声明质量。
- Human-in-the-loop: 高风险或质量不达标时进入人工审核。
- Checkpoint Resume: AgentState 可持久化，人工审核后可从 checkpoint 恢复运行。
- Observability Dashboard: 前端展示 session、trace、metrics、Human Gate 和最终结果。

## 运行方式

安装后端依赖：

```bash
pip install -r requirements.txt
```

启动后端：

```bash
uvicorn backend.main:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

Dashboard:

```text
http://localhost:5173
```

运行测试：

```bash
python -m pytest tests
```

前端构建：

```bash
cd frontend
npm run build
```

## Deployment

部署说明详见 [docs/deployment.md](docs/deployment.md)。

### Deployment URLs

本地开发地址：

```text
Backend URL: http://127.0.0.1:8000
Frontend URL: http://localhost:5173
```

线上部署时建议替换为：

```text
Backend URL: https://api.your-domain.com
Frontend URL: https://crisis-agent.your-domain.com
```

### Backend

安装依赖：

```bash
pip install -r requirements.txt
```

本地或服务器直接启动：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Docker 构建：

```bash
docker build -t crisis-agent-backend .
```

Docker 运行：

```bash
docker run -p 8000:8000 --env-file .env crisis-agent-backend
```

后端环境变量示例见 `.env.example`：

```env
AGENT_MODE=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

生产环境建议设置：

```env
CORS_ORIGINS=https://your-frontend-domain.com
```

### Environment Variables

Backend:

```env
AGENT_MODE=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
CORS_ORIGINS=https://your-frontend-domain.com
```

Frontend:

```env
VITE_API_BASE_URL=https://api.your-domain.com
```

### Frontend

进入前端目录：

```bash
cd frontend
```

安装依赖：

```bash
npm install
```

本地开发：

```bash
npm run dev
```

生产构建：

```bash
npm run build
```

前端环境变量示例见 `frontend/.env.example`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

本地开发时可以不配置 `VITE_API_BASE_URL`，Vite 会通过 proxy 转发 `/api` 到后端。生产部署时建议配置为后端 API 域名，例如：

```env
VITE_API_BASE_URL=https://your-backend-domain.com
```

### Demo Usage

运行面试 Demo：

```bash
python scripts/run_demo_cases.py
```

Demo 默认使用 mock 模式，保证输出稳定。如果需要展示真实 LLM：

```bash
AGENT_MODE=llm python scripts/run_demo_cases.py
```

## Demo Cases

项目内置了 3 个固定展示案例，适合 GitHub 演示和面试讲解：

- `food_safety`: 食品品牌被爆使用过期原料。
- `data_privacy`: APP 用户信息泄露。
- `service_failure`: 互联网平台大面积服务故障。

案例文件：

```text
demo/cases.json
```

运行 Demo：

```bash
python scripts/run_demo_cases.py
```

脚本会依次输出：

- case 名称
- dynamic runtime 结果
- plan
- agent trace
- RAG 命中
- memory 命中
- evaluation
- human gate 状态
- final statement

## API 简要说明

固定危机 workflow：

- `POST /api/crisis/run`
- `GET /api/crisis/sessions`
- `GET /api/crisis/sessions/{session_id}`

Dynamic Runtime：

- `POST /api/dynamic/run`
- `GET /api/dynamic/sessions`
- `GET /api/dynamic/{session_id}`
- `POST /api/dynamic/{session_id}/approve`
- `POST /api/dynamic/{session_id}/reject`
- `GET /api/dynamic/{session_id}/metrics`

示例：

```json
{
  "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
}
```

## 项目亮点

面试时可以这样概括：

CrisisAgent 的亮点不在于简单调用一个大模型，而是把企业危机公关拆成一个工程化 Agent 系统。它有动态规划、执行器、共享状态、RAG 合规知识、历史经验 Memory、工具调用、上下文管理、离线评测、人工审核和 checkpoint resume。每一步都有 trace 和 metrics，因此不仅能生成结果，还能解释结果是怎么来的、哪里失败了、是否需要人工介入，以及如何从中断状态恢复。

这让项目从 demo 更接近真实生产系统：可替换模型、可观察、可评估、可恢复、可逐步扩展。

## 文档

- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Agent Runtime](docs/agent-runtime.md)
- [Interview Notes](docs/interview-notes.md)
