# API

## Health Check

```http
GET /health
```

返回：

```json
{
  "status": "ok"
}
```

## 固定 Crisis Workflow

### POST /api/crisis/run

运行固定 A/C/D/B/C/E workflow。

请求：

```json
{
  "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
}
```

返回核心字段：

```json
{
  "session_id": "...",
  "final_statement": "...",
  "scores": {
    "legal_safety": 8,
    "empathy": 8,
    "robustness": 8
  },
  "agent_trace": []
}
```

### GET /api/crisis/sessions

返回固定 workflow 的 session 摘要列表。

### GET /api/crisis/sessions/{session_id}

返回固定 workflow 的完整 session。

不存在时返回 404。

## Dynamic Runtime API

### POST /api/dynamic/run

创建动态 Agent Runtime 任务。

请求：

```json
{
  "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
}
```

返回核心字段：

```json
{
  "session_id": "...",
  "plan_id": "...",
  "event": "...",
  "status": "waiting_human",
  "state_status": "WAITING_HUMAN",
  "approval": {
    "required": true,
    "decision": "pending",
    "reason": "Human review required: high_risk"
  },
  "results": {},
  "execution_trace": []
}
```

### GET /api/dynamic/sessions

返回 Dynamic Runtime checkpoint session 列表。

字段包括：

- session_id
- plan_id
- event
- status
- created_time

### GET /api/dynamic/{session_id}

返回完整 AgentState。

核心字段：

- session_id
- plan_id
- event
- status
- results
- trace
- metadata
- approval
- failed_agents
- current_agent

trace 会在 API 层增强：

- duration_ms
- input_summary
- output_summary
- error

### POST /api/dynamic/{session_id}/approve

人工审核通过，并尝试 resume runtime。

请求：

```json
{
  "reviewer": "alice",
  "comment": "确认可以继续执行"
}
```

状态变化：

```text
WAITING_HUMAN
  ↓
RUNNING
  ↓
resume_agent_loop
```

### POST /api/dynamic/{session_id}/reject

人工审核拒绝，并终止 runtime。

请求：

```json
{
  "reviewer": "bob",
  "comment": "声明风险过高，拒绝发布"
}
```

状态变化：

```text
WAITING_HUMAN
  ↓
FAILED
```

### GET /api/dynamic/{session_id}/metrics

返回 runtime 可观测指标。

返回：

```json
{
  "session_id": "...",
  "total_duration": 750,
  "agent_count": 5,
  "failed_agents": [],
  "rag_hits": 1,
  "memory_hits": 1,
  "tool_calls": 1,
  "human_status": {
    "state_status": "WAITING_HUMAN",
    "required": true,
    "decision": "pending",
    "reason": "Human review required: high_risk"
  }
}
```

## Swagger

启动后端后访问：

```text
http://127.0.0.1:8000/docs
```
