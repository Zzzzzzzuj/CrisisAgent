# CrisisAgent

CrisisAgent 是一个面向企业危机公关场景的多智能体决策系统。它不是简单生成一段公关稿，而是把“事件研判、声明生成、合规审查、人工审核、过程追踪、离线评测”组织成一套可演示、可解释、可扩展的 Agent Platform。

当前版本已完成 FastAPI 后端、Dynamic Agent Runtime、Hybrid RAG、Memory、Tool Calling、Evaluation、Human-in-the-loop、Checkpoint Resume 和 Vue Dashboard。

## Product Preview

> 截图建议：启动前端后截取“危机案例管理中心”和“案例详情页”，保存到 `docs/images/dashboard-home.png` 和 `docs/images/case-detail.png`。

```text
Crisis Case 管理中心
  - 危机标题
  - 风险等级
  - AI 生成声明
  - 审核状态

案例详情页
  - 舆情分析
  - AI 声明
  - Human Review
  - 高级分析：Agent Trace / RAG / Memory
```

## Demo Flow

项目内置 3 个面试展示案例：

- 食品安全：过期原料偷拍视频传播，公众要求监管介入。
- 数据泄露：APP 用户信息疑似泄露，引发投诉。
- 普通投诉：门店排队时间过长，在本地社群传播。

命令行 Demo：

```bash
python scripts/run_demo_cases.py
```

Dashboard Demo：

```bash
uvicorn backend.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://localhost:5173
```

推荐演示顺序：

1. 打开首页，说明系统以 Crisis Case 为核心，而不是技术 session。
2. 新建食品安全案例，展示 AI 如何生成声明和审核状态。
3. 进入详情页，讲解风险等级、舆情分析、AI 声明和 Human Review。
4. 展开高级分析，展示 Agent Trace、RAG、Memory 和 Metrics。

## Architecture

```text
User Crisis Event
  ↓
Planner
  ↓
Plan Validator
  ↓
Executor
  ↓
AgentState
  ↓
Agent Adapter
  ↓
Agents
  ↓
RAG / Memory / Tools / Context
  ↓
Evaluation
  ↓
Human Gate
  ↓
Checkpoint
  ↓
Resume
  ↓
Dashboard
```

更多架构图见 [docs/architecture-diagram.md](docs/architecture-diagram.md)。

## Core Capabilities

- Dynamic Agent Runtime: Planner 生成执行计划，Validator 修正依赖，Executor 执行 Agent。
- Multi Agent Collaboration: 舆情分析、文案生成、红队攻击、合规审查、最终决策分工明确。
- Hybrid RAG: Agent B 合规审查可检索本地法规与危机回应知识库。
- Memory System: 从历史 session 抽取企业危机经验，支持后续复用。
- Tool Calling: 统一 Tool 抽象，让 Agent 可调用外部能力。
- Context Engineering: Writer Agent 使用 ContextManager 管理上下文优先级。
- Evaluation System: 覆盖 workflow、RAG、Memory、Response Quality 和 LLM-as-Judge。
- Human-in-the-loop: 高风险或低质量结果进入人工审核。
- Checkpoint Resume: 审核后可从 checkpoint 恢复 Agent Loop。
- Observability Dashboard: 前端展示案例、声明、审核、Trace、Metrics。

## Tech Stack

- Backend: Python, FastAPI, Pydantic, pytest
- Runtime: Planner, Executor, AgentState, Adapter, Human Gate, Checkpoint Resume
- LLM Infra: OpenAI-compatible HTTP client, Prompt Loader, JSON Parser, mock/llm dual mode
- RAG: Keyword Retriever, Vector Retriever, Hybrid Retriever, Rule-based Reranker
- Memory: Local JSON storage and keyword retrieval
- Frontend: Vue3, Vite, Axios
- Deployment: Dockerfile, environment-based CORS, Vite API base URL

## Quick Start

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Start backend:

```bash
uvicorn backend.main:app --reload
```

Start frontend:

```bash
cd frontend
npm install
npm run dev
```

Run tests:

```bash
python -m pytest tests
```

Build frontend:

```bash
cd frontend
npm run build
```

## API

Fixed workflow:

- `POST /api/crisis/run`
- `GET /api/crisis/sessions`
- `GET /api/crisis/sessions/{session_id}`

Dynamic Runtime:

- `POST /api/dynamic/run`
- `GET /api/dynamic/sessions`
- `GET /api/dynamic/{session_id}`
- `POST /api/dynamic/{session_id}/approve`
- `POST /api/dynamic/{session_id}/reject`
- `GET /api/dynamic/{session_id}/metrics`

## Deployment

Deployment guide: [docs/deployment.md](docs/deployment.md)

Backend:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm run build
```

Docker:

```bash
docker build -t crisis-agent-backend .
docker run -p 8000:8000 --env-file .env crisis-agent-backend
```

## Interview Highlights

面试时可以这样介绍：

CrisisAgent 的核心不是“调用一个大模型生成公关稿”，而是把企业危机响应拆成一个工程化 Agent 系统。它有动态规划、执行器、共享状态、RAG 合规知识、历史经验 Memory、工具调用、上下文管理、离线评测、人工审核和 checkpoint resume。每一步都有 trace 和 metrics，因此不仅能生成结果，还能解释结果是怎么来的、哪里失败了、是否需要人工介入，以及如何从中断状态恢复。

## Docs

- [Architecture Diagram](docs/architecture-diagram.md)
- [Demo Guide](docs/demo-guide.md)
- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Agent Runtime](docs/agent-runtime.md)
- [Deployment](docs/deployment.md)
- [Interview Notes](docs/interview-notes.md)
