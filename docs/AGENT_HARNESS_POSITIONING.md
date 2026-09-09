# Agent Harness Positioning

CrisisAgent is an Agent Harness: it provides bounded data inputs, workflow state, checkpoints, trace, tool policy, Human Review, and evaluation around model-assisted steps. It is not an unrestricted autonomous agent and does not expose publication or approval actions as tools.

The Watchlist layer demonstrates the same principle for monitoring: deterministic query construction, allowlisted providers, explicit live-fetch controls, Public Signals, alerts, and offline bad-case evaluation. The harness makes behavior inspectable and gives operators a controlled handoff to the existing CrisisEvent and Agent workflow.

## Interview points

- Multi-Agent Workflow makes role dependencies and review gates explicit; autonomous planning is not required for every step.
- State and checkpoints make a run resumable, while Trace explains inputs, outputs, evidence, and failures.
- ToolRunner validates schemas, bounds retries and runtime, and records structured errors.
- Prompt Injection and excessive agency are handled with policy boundaries and Human Review rather than prompt text alone.
- RAG and monitoring evaluation measure retrieval and signal quality instead of only showing a successful demo.
- Case Memory and ContextPack separate durable reviewed case summaries from short-lived AgentState and bound the context passed to later steps.
