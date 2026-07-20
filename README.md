# CrisisAgent MVP

这是一个面向企业危机公关场景的最小可运行后端 MVP，使用 `FastAPI + Python` 实现多智能体 workflow 骨架。

当前版本不接入真实大模型，也不包含前端。所有 Agent 都是规则函数 / mock 输出，目标是先跑通后端流程、接口和 `agent_trace`。

## 项目结构

```text
backend/
  agents/
    decision_agent.py
    legal_agent.py
    redteam_agent.py
    sentiment_agent.py
    writer_agent.py
  __init__.py
  main.py
  schemas.py
  storage.py
  workflow.py
cases/
  sample_cases.json
requirements.txt
README.md
```

## 安装依赖

建议先创建虚拟环境，再安装依赖：

```bash
pip install -r requirements.txt
```

## 启动服务

在项目根目录执行：

```bash
uvicorn backend.main:app --reload
```

启动后默认访问地址：

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- 健康检查: `http://127.0.0.1:8000/health`

## 在 Swagger 测试 `/api/crisis/run`

1. 启动服务后，打开 `http://127.0.0.1:8000/docs`
2. 找到 `POST /api/crisis/run`
3. 点击 `Try it out`
4. 输入示例请求：

```json
{
  "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
}
```

5. 点击 `Execute`
6. 你会看到包含以下字段的响应：
   - `session_id`
   - `final_statement`
   - `scores`
   - `agent_trace`

## Workflow 说明

当前 workflow 固定为：

1. Agent A - 舆情分析 Agent
2. Agent C - 策略文案 Agent（第一版）
3. Agent D - 红队攻击 Agent
4. Agent B - 合规审查 Agent
5. Agent C - 策略文案 Agent（第二版）
6. Agent E - 最终决策 Agent

其中：

- `main.py` 只负责接收请求并返回响应
- `workflow.py` 是唯一的流程编排入口
- 每个 Agent 文件只暴露清晰函数，便于后续替换为真实 LLM 调用

## 当前版本的 Mock 特性

- 舆情分析基于关键词规则判断风险和情绪
- 文案 Agent 输出固定模板并根据上下文做轻量调整
- 红队 Agent 返回可能的舆论攻击点
- 合规 Agent 返回法律风险与修订建议
- 决策 Agent 生成最终声明并给出规则分数

## 后续替换为真实 LLM 的建议

后续如果接入真实模型，建议优先替换这些文件中的函数实现：

- `backend/agents/sentiment_agent.py`
- `backend/agents/writer_agent.py`
- `backend/agents/redteam_agent.py`
- `backend/agents/legal_agent.py`
- `backend/agents/decision_agent.py`

对外接口和 `workflow.py` 的主流程可以保持不变，这样前后端联调成本会更低。
