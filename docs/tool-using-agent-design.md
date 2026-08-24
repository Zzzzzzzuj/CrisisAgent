# Tool-Using Legal Agent Design

Phase 19 adds an optional Tool-Using Legal Agent experiment. It does not replace the existing Legal Agent or rewrite the main workflow.

## Why Not a Fully Autonomous Agent

Crisis response is high-risk. A fully autonomous agent that can freely choose to skip Legal Review, Guardrails or Human Review would be unsafe.

This project uses controlled autonomy:

- workflow remains the default business path
- high-risk cases must keep Legal RAG and Guardrail checks
- sensitive actions such as publish, approve and reject are blocked from LLM tool calls
- tool calls are schema-validated and traced

## ReAct Idea in This Project

The ReAct pattern is usually:

```text
Reason -> Act with tool -> Observe -> Reason again
```

In CrisisAgent Phase 19:

- Reason: build a structured tool plan from event, sentiment and redteam context
- Act: execute allowed skills through `FunctionCallingAdapter`
- Observe: collect tool outputs and tool_call_trace
- Final: produce legal_risks, safe_points, revision_advice and human_review_required

The current implementation is deterministic and mock/offline friendly. It does not require a real LLM.

## Function Calling, Skill and MCP Mock

- `AgentSkill` is the internal capability description.
- `FunctionCallingAdapter` converts skills to OpenAI-compatible function/tool schemas and executes them by name.
- `MCPAdapter` maps skills to MCP-like tool/resource specs for explanation and tests.
- The Tool-Using Legal Agent uses the Skill Registry and Function Calling Adapter, not a real MCP server.

## Tool Safety Rules

Tool policy lives in:

```text
backend/core/tool_policy.py
```

Rules:

- high-risk cases cannot skip `legal_rag_search`
- high-risk cases cannot skip `guardrail_check`
- sensitive actions such as `publish`, `approve` and `reject` cannot be called by the LLM/tool planner
- all tool arguments must be JSON objects
- tool arguments are schema validated before execution
- every tool result is written to `tool_call_trace`

## Structured Tool Plan

The controlled planner outputs:

```json
{
  "reasoning_mode": "strict",
  "risk_reasons": ["high_risk", "legal_or_regulatory_signal"],
  "required_agents": ["legal"],
  "required_tools": ["legal_rag_search", "guardrail_check"],
  "human_review_required": true,
  "validation_notes": []
}
```

For low-risk cases, `legal_rag_search` may be skipped, but the skip reason must be recorded.

## Why PlanValidator and Human Review Still Matter

The tool-using agent is not allowed to become the final authority. High-risk cases still require validation and Human Review because:

- tool planning can be wrong
- retrieved evidence can be incomplete
- LLM output can be structurally unstable
- legal/public statements need auditability

## Current Limits

- This is an optional experiment, not the default Legal Agent.
- It does not call a real LLM.
- It does not connect to a real MCP server.
- It does not autonomously approve, reject or publish.
- It is intended to explain ReAct / Function Calling / Tool Observation / Tool Safety in a controlled workflow system.
