# Agent Runtime

## 为什么需要 Dynamic Runtime

固定 workflow 适合稳定业务链路，但真实危机场景可能需要根据事件类型、风险等级和合规需求动态决定执行哪些 Agent。

Dynamic Runtime 的目标是让系统具备更强的可扩展性：

- Planner 负责生成计划。
- Plan Validator 负责补齐依赖和修正顺序。
- Executor 负责执行 Agent。
- AgentState 负责共享状态。
- Human Gate 负责人工审核。
- Checkpoint 负责持久化。
- Resume 负责从审核后状态继续执行。

## 核心数据流

```text
event
  ↓
Planner
  ↓
Plan Validator
  ↓
AgentState(session_id, plan_id, event)
  ↓
Executor
  ↓
Adapter
  ↓
Agent.run(...)
  ↓
state.set_result(...)
  ↓
state.add_trace(...)
  ↓
RuntimeEvaluator
  ↓
Policy
  ↓
Human Gate
  ↓
Checkpoint
  ↓
Resume
```

## Planner

文件：

```text
backend/agents/planner_agent.py
```

输入：

```json
{
  "event": "...",
  "category": "food_safety",
  "risk_level": "high"
}
```

输出：

```json
{
  "plan_id": "...",
  "plan": [
    {
      "agent": "sentiment",
      "reason": "...",
      "confidence": 0.9
    }
  ]
}
```

第一版是 rule-based，不调用 LLM。

## Plan Validator

文件：

```text
backend/core/plan_validator.py
```

职责：

- 校验非法 Agent。
- 自动补充依赖。
- 修正执行顺序。

例如 legal 依赖 writer 和 redteam，如果 Planner 只给了 legal，Validator 会补齐：

```text
sentiment → writer → redteam → legal → decision
```

## Executor

文件：

```text
backend/core/executor.py
```

职责：

- 按 plan 顺序执行 Agent。
- 通过 Adapter 构造每个 Agent 的输入。
- 成功时写入 `state.results`。
- 失败时写入 `state.failed_agents`，但不让整个 runtime 崩溃。
- 每一步写入 trace。

## AgentState

文件：

```text
backend/core/state.py
```

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

AgentState 是 Dynamic Runtime 的共享上下文。Agent 之间不直接互相调用，而是通过 state 传递结果。

## Adapter

文件：

```text
backend/core/adapter.py
```

不同 Agent 的输入 schema 不一样，Adapter 负责从 AgentState 构造输入：

- sentiment: event
- writer: event + sentiment_analysis + memory_context
- redteam: event + draft
- legal: event + draft + redteam_review
- decision: event + results

这样可以保持 Agent 原有 `run(...)` 接口不变。

## Human Gate

相关文件：

```text
backend/core/policy.py
backend/core/human.py
backend/core/runtime_evaluator.py
```

职责拆分：

- RuntimeEvaluator 只判断质量是否通过。
- Policy 判断是否需要人工审核。
- Human 模块负责 approve/reject 状态流转和 trace。

状态机：

```text
INIT
  ↓
RUNNING
  ↓
WAITING_HUMAN
  ↓ approve
RUNNING

WAITING_HUMAN
  ↓ reject
FAILED
```

## Checkpoint Resume

相关文件：

```text
backend/core/checkpoint.py
backend/core/resume.py
```

Checkpoint 保存完整 AgentState：

- results 不丢失
- trace 不丢失
- approval 不丢失
- plan_id 不丢失
- session_id 不丢失

Resume 流程：

```text
session_id
  ↓
load_checkpoint
  ↓
restore AgentState
  ↓
check approval
  ↓
resume_agent_loop
```

## Observability

Dashboard 使用 trace 和 metrics 展示 Runtime 生命周期。

Trace 关注单步：

- agent
- status
- duration_ms
- input_summary
- output_summary
- error

Metrics 关注整体：

- total_duration
- agent_count
- failed_agents
- rag_hits
- memory_hits
- tool_calls
- human_status
