# Agent Tool Reliability

## Why tool calling alone is not enough

“The Agent can call a tool” only proves that a handler can be reached. A reliable Agent system also needs a clear tool contract, input/output validation, timeout behavior, retry limits, fallback semantics, structured errors and trace data.

## Current layer

CrisisAgent already has:

- `backend/skills/skill_schema.py`: `AgentSkill` and compatible `ToolDefinition` metadata;
- `backend/skills/registry.py`: registration, enablement and input validation;
- `backend/skills/function_calling_adapter.py`: OpenAI-compatible tool schema and tool-call trace;
- `backend/core/tool_policy.py`: high-risk required tools and sensitive-action denial;
- `backend/agents/tool_using_legal_agent.py`: a separate controlled tool-using experiment path.

The first reliability layer adds `backend/skills/tool_runner.py`. It is deliberately independent from the main Executor and does not replace the existing Legal Agent or Workflow.

## Execution Budget / Loop Prevention

Tool calls need an execution budget before a future planner is allowed to issue multiple steps. Without one, a retrying or self-correcting loop could repeat the same tool call indefinitely, increase latency, or consume resources without producing new information.

`ToolExecutionBudget` currently limits:

- `max_steps`：最多执行多少个逻辑工具步骤；
- `max_retries`：预算允许的总重试次数；
- `max_runtime_ms`：整个预算实例允许的运行时间；
- `max_same_call`：同一个 tool 加同一组规范化 arguments 允许重复的次数。

Arguments are serialized with sorted keys and hashed. If the same tool and normalized arguments exceed `max_same_call`, the budget returns `TOOL_LOOP_DETECTED` before the handler runs. Step、retry 和 runtime 超限分别返回 `TOOL_BUDGET_EXCEEDED`、`TOOL_RETRY_BUDGET_EXCEEDED` 和 `TOOL_RUNTIME_BUDGET_EXCEEDED`。这些结果会进入 `ToolResult`，并设置 `human_review_required=true`，因为系统无法证明继续重复执行是安全的。

当前预算只服务于 ToolRunner 旁路实验路径，不接入主 Executor，也不把项目改成 ReAct。未来如果要接入更动态的工具规划，必须先保留预算、重复调用检测和失败 trace，再评估主运行时集成。

离线工具可靠性评测见 [`TOOL_RELIABILITY_EVAL.md`](TOOL_RELIABILITY_EVAL.md)。

### 面试讲解版

> 我给工具执行增加了四层预算：最大 step、最大 retry、最大 runtime 和同参重复调用次数。每次工具调用前都会把参数规范化并计算 hash，如果同一个工具用同样参数重复执行，就返回 `TOOL_LOOP_DETECTED`，而不是继续调用。预算超限不会静默失败，会返回结构化错误并建议进入人工审核。第一阶段只在 ToolRunner 旁路验证，避免为了展示 ReAct 而改动主 Workflow。

## ToolDefinition

Each tool can describe:

```text
name / description
input_schema / output_schema
category / owner_agent
safety_level / risk_level
read_only
requires_human_confirmation
timeout_ms / max_retries
fallback_policy
enabled / version
handler
```

The default registry contains read-only or analysis capabilities such as Legal RAG search, session lookup, metrics query, guardrail check and knowledge document search. Approval, rejection, publishing, notification, deletion and knowledge-base mutation are intentionally not registered as model-callable default tools.

## ToolRunner execution order

```text
tool lookup
→ enabled check
→ input schema validation
→ policy / safety check
→ bounded handler execution
→ output schema validation
→ retry within max_retries
→ optional fallback
→ structured ToolResult + trace
```

`ToolResult` records `success`, `output`, `error_code`, `attempts`, `retry_count`, `fallback_used`, `human_review_required` and trace metadata such as duration. Tool failure becomes a structured result rather than an unhandled exception.

## Error recovery

The first error vocabulary includes:

```text
TOOL_NOT_FOUND
TOOL_DISABLED
TOOL_INPUT_INVALID
TOOL_OUTPUT_INVALID
TOOL_TIMEOUT
TOOL_RETRY_EXHAUSTED
TOOL_EXECUTION_FAILED
TOOL_POLICY_DENIED
TOOL_FALLBACK_FAILED
```

Retry is bounded by the tool definition. A fallback is explicit and validated against the same output schema. Timeout handlers are tested with fake functions; this phase does not call real networks, LLMs, databases, Redis or BGE.

## Why the main Executor is unchanged

The ToolRunner is first validated in the Tool-Using Legal Agent experiment path. The fixed Workflow, Dynamic Runtime Executor and main Legal Agent remain unchanged. This keeps the existing API and Agent ordering stable while allowing tool contracts and recovery behavior to mature independently.

## Current boundaries

This phase is not a ReAct rewrite, distributed tool platform or MCP Server. The planner remains controlled and the default registry does not expose approve/reject/publish or other irreversible actions. A future phase can add execution budgets and repeated-call detection before considering any main-runtime integration.

## Interview version

> I did not stop at exposing a function as a tool. I first described each tool's input/output schema, read-only and risk metadata, timeout and retry budget. Then I added a standalone ToolRunner that validates input, bounds execution, validates output, retries only within the declared budget, optionally falls back, and returns a structured error code and trace. I kept it on the Tool-Using Legal Agent experiment path rather than changing the production workflow, so the reliability mechanism can be tested offline without changing existing business behavior.
