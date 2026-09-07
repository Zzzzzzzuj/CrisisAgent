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
