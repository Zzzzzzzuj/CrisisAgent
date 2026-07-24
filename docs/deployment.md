# Deployment

本文档说明 CrisisAgent 的本地运行、Docker 运行和线上部署步骤。部署准备只涉及服务配置，不改变 Agent Runtime 业务逻辑。

## 1. 本地运行

### Backend

安装依赖：

```bash
pip install -r requirements.txt
```

启动 FastAPI：

```bash
uvicorn backend.main:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

### Frontend

安装依赖：

```bash
cd frontend
npm install
```

启动 Vite：

```bash
npm run dev
```

默认地址：

```text
http://localhost:5173
```

本地开发时，Vite proxy 会将 `/api` 转发到后端。也可以通过 `frontend/.env` 设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 2. Docker 运行 Backend

构建镜像：

```bash
docker build -t crisis-agent-backend .
```

运行容器：

```bash
docker run -p 8000:8000 --env-file .env crisis-agent-backend
```

容器启动命令：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

注意：当前开发机器如果未安装 Docker CLI，需要在安装 Docker Desktop 或服务器 Docker 环境后执行上述命令。

## 3. 线上部署步骤

### Backend

推荐环境变量：

```env
AGENT_MODE=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
CORS_ORIGINS=https://your-frontend-domain.com
```

部署后端服务：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

线上 Backend URL 示例：

```text
https://api.your-domain.com
```

需要确认：

- `/health` 返回 `{"status":"ok"}`。
- `/docs` 可访问或按生产安全策略关闭。
- `CORS_ORIGINS` 包含前端域名。
- `AGENT_MODE=mock` 时不需要 LLM Key。
- `AGENT_MODE=llm` 时必须配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。

### Frontend

生产环境配置：

```env
VITE_API_BASE_URL=https://api.your-domain.com
```

构建：

```bash
cd frontend
npm install
npm run build
```

部署目录：

```text
frontend/dist/
```

线上 Frontend URL 示例：

```text
https://crisis-agent.your-domain.com
```

## 4. Demo Usage

运行固定 Demo Case：

```bash
python scripts/run_demo_cases.py
```

Demo 包含：

- `food_safety`
- `data_privacy`
- `service_failure`

脚本默认使用 `AGENT_MODE=mock`，适合稳定展示。如果要演示真实 LLM，可显式设置：

```bash
AGENT_MODE=llm python scripts/run_demo_cases.py
```

Windows PowerShell：

```powershell
$env:AGENT_MODE="llm"
python scripts/run_demo_cases.py
```

## 5. 部署检查清单

- Backend 可以导入 `backend.main:app`。
- Backend 可以通过 `uvicorn backend.main:app` 启动。
- CORS middleware 已启用。
- `CORS_ORIGINS` 指向前端域名。
- Frontend `VITE_API_BASE_URL` 指向后端 API。
- `npm run build` 成功生成 `frontend/dist/`。
- `python -m pytest tests` 全部通过。
