# Tool Calling, MCP, Skills and A2A

CrisisAgent adds a lightweight skills layer to explain common Agent engineering concepts without turning the project into a full MCP platform.

## Function Calling

Function Calling is the LLM-facing tool contract. A model receives tool schemas, decides whether to call a tool and returns structured tool-call arguments.

In this project:

- `backend/skills/skill_schema.py` defines `AgentSkill`.
- `backend/skills/function_calling_adapter.py` converts an `AgentSkill` into an OpenAI-compatible `tools=[{type:function,...}]` schema.
- The adapter can validate input and execute a skill by name.
- It records `tool_call_trace`.
- It does not call a real LLM.

## MCP

MCP is a protocol for connecting agents to tools and resources through an external server/runtime.

In this project:

- `backend/skills/mcp_adapter.py` defines `MCPToolSpec`, `MCPResourceSpec` and `MCPCallResult`.
- `skill_to_mcp_tool()` maps `AgentSkill` metadata into an MCP-like tool spec.
- `mock_mcp_call()` simulates a call for tests and docs.
- No real MCP SDK or external MCP server is used.

This is an MCP-compatible abstraction, not a complete MCP runtime.

## Skill

A skill is a project-level capability description that can be exposed through different protocols.

`AgentSkill` includes:

- `name`
- `description`
- `input_schema`
- `output_schema`
- `category`
- `owner_agent`
- `safety_level`
- `enabled`
- `version`

Built-in skills:

- `legal_rag_search`
- `session_lookup`
- `runtime_metrics_query`
- `guardrail_check`
- `knowledge_document_search`

## A2A

A2A means agent-to-agent communication. It is different from MCP:

- MCP: an agent calls tools or reads resources.
- A2A: agents exchange tasks, context and acknowledgements.

In this project:

- `backend/skills/a2a_schema.py` defines `AgentMessage`.
- Current runtime still uses shared `AgentState`.
- `AgentMessage` documents how Planner, Executor and Agents could exchange explicit messages later.

## Concept Mapping

| Concept | CrisisAgent implementation |
| --- | --- |
| Function Calling | `FunctionCallingAdapter` maps `AgentSkill` to OpenAI-compatible tool schema |
| MCP Tool | `MCPToolSpec` mock mapping from `AgentSkill` |
| MCP Resource | `MCPResourceSpec` for skill metadata resources |
| Skill | `AgentSkill` registry with built-in capabilities |
| A2A | `AgentMessage` schema for future agent-to-agent task messages |

## Why Not Real MCP Yet

The goal of this project phase is interview clarity and protocol boundaries, not platform migration.

The current implementation avoids real MCP because:

- ordinary pytest must remain offline
- no external MCP server is needed for the demo
- Agent business flow should remain stable
- the project only needs a thin adapter layer to explain how Function Calling, MCP, Skills and A2A differ

Future production work could connect `AgentSkill` to a real MCP server if the project needs external tool/resource orchestration.
