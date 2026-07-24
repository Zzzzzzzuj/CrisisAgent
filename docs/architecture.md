# Architecture

## 项目解决的问题

CrisisAgent 面向企业危机公关场景，目标是帮助企业在突发负面事件中快速完成舆情判断、回应草稿、风险攻击、合规审查、最终决策和人工审核。

传统“一个 Prompt 生成最终声明”的方式很难满足真实业务需要，因为危机公关不是单点生成任务，而是一条风险控制链路。CrisisAgent 将这条链路工程化，使每个步骤都能被测试、观察、替换和评估。

## 为什么采用多 Agent 架构

多 Agent 的核心价值是职责拆分：

- Agent A 负责舆情分析，判断风险、情绪和回应语气。
- Agent C 负责策略文案，生成第一版和第二版声明。
- Agent D 负责红队攻击，模拟公众质疑和媒体追问。
- Agent B 负责合规审查，结合 RAG 知识库降低法律表达风险。
- Agent E 负责最终决策，输出最终声明和评分。

如果只用一个 LLM，所有能力会混在同一个 Prompt 里，很难定位错误，也很难单独增强合规、评测、工具调用或人工审核。

## 总体架构图

```text
User Event
  ↓
FastAPI
  ↓
Dynamic Runtime
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
Runtime Evaluator
  ↓
Human Gate
  ↓
Checkpoint
  ↓
Resume
  ↓
Dashboard / Evaluation
```

固定 workflow 仍然保留：

```text
用户输入事件
  ↓
FastAPI
  ↓
workflow.py
  ↓
Agent A 舆情分析
  ↓
Agent C 第一版文案
  ↓
Agent D 红队攻击
  ↓
Agent B 合规审查
  ↓
Agent C 第二版文案
  ↓
Agent E 最终决策
  ↓
agent_trace
```

## 后端结构

```text
backend/
  main.py
  workflow.py
  schemas.py
  storage.py
  agents/
  core/
  rag/
  memory/
  tools/
  context/
  prompts/
  llm_client.py
  prompt_loader.py
  config.py
  logger.py
```

关键职责：

- `backend/main.py`: FastAPI API 层，负责接收请求和返回响应。
- `backend/workflow.py`: 固定 A/C/D/B/C/E workflow 编排入口。
- `backend/agents/`: 每个 Agent 的 mock/llm 双模式逻辑。
- `backend/core/`: Dynamic Runtime，包括 Planner、Executor、AgentState、Human Gate、Checkpoint、Resume。
- `backend/rag/`: RAG 检索基础设施，包括 keyword、vector、hybrid 和 reranker。
- `backend/memory/`: 企业历史危机经验记忆。
- `backend/tools/`: Tool 抽象和 Tool Registry。
- `backend/context/`: ContextManager，用于上下文优先级和 token 控制。
- `evaluation/`: 离线评测体系。
- `frontend/`: Vue Dashboard。

## LLM / Mock 双模式

每个 Agent 保持稳定接口，例如：

```python
run(payload) -> dict
```

内部根据 `AGENT_MODE` 选择：

```text
mock:
  rule/mock function

llm:
  load_prompt
  ↓
  call_llm
  ↓
  parse_llm_json
  ↓
  validate
  ↓
  normalize
```

这样做的好处是 API 和 workflow 不需要因为模型接入而改变。

## Fallback 机制

LLM 模式下，如果发生网络异常、超时、JSON 解析失败、字段缺失或类型错误，Agent 会 fallback 到 mock 逻辑。fallback 会记录日志和 trace，保证整体流程不中断。

## RAG / Memory / Tools

RAG 主要服务 Agent B 合规审查：

```text
event + draft + redteam_review
  ↓
retrieval query
  ↓
HybridRetriever
  ↓
Reranker
  ↓
legal_context
  ↓
Legal Agent Prompt
```

Memory 主要服务 Agent C 文案生成，让它参考历史危机经验，但不直接复制历史声明。

Tools 用于给 Agent 提供外部能力，目前包括舆情分析工具和法规检索工具。

## Trace 和 Metrics

Dynamic Runtime 的 trace 记录：

- agent
- status
- start_time
- end_time
- duration_ms
- input_summary
- output_summary
- error

Metrics 接口统计：

- total_duration
- agent_count
- failed_agents
- rag_hits
- memory_hits
- tool_calls
- human_status

这些信息支撑 Dashboard 展示和故障排查。

## Evaluation 体系

Evaluation 模块不依赖前端，也不改变业务 API。它通过离线 case 调用 workflow/runtime，生成 JSON 和 Markdown 报告。

当前评测覆盖：

- 风险识别准确率
- 情绪识别准确率
- tone accuracy
- RAG recall@k
- MRR
- rerank gain
- memory hit rate
- response quality
- hallucination risk
