# Legal Action / Observation Loop

This is a bounded Legal-stage control flow for Dynamic Runtime, not a new agent or a general planner. The fixed six-role workflow remains unchanged. The program computes eligible actions from the current Claim state. If there is one eligible action, the program proceeds without an LLM proposal; when multiple meaningful actions are eligible, the Legal LLM may propose one and a program validator must allow it before execution. The model proposes; the program owns execution. The loop reuses claim-targeted Legal RAG, Claim Coverage, and Human Fact pause/resume.

## Runtime Flow

```text
Legal Claim Extraction + current Relation/Coverage
  -> program computes eligible actions
  -> one eligible action: proceed directly
  -> multiple meaningful actions: Legal LLM proposal -> program validation
  -> execute one bounded, validated action
  -> update Relation/Coverage from the observation
  -> update Claim Progress and recompute eligible actions
  -> continue, request human facts, or stop
```

An observation can change the next action. For example, when a targeted legal search finds a relevant rule, the claim coverage changes to `candidate_found`; P32 no longer recommends searching that same gap, and the loop uses the available rule candidate or stops. If there are multiple distinct legal-rule gaps, the next retrieval is for the next claim and its record includes the preceding observation. The loop will not repeat retrieval for the same claim/gap after a no-hit or failure.

Case-fact gaps are not sent to Legal RAG. They produce a claim-scoped `REQUEST_HUMAN_FACT`, after which the existing Dynamic Runtime checkpoint path waits for a human response. The response becomes a structured Observation and resumes the same bounded Legal loop from its saved cursor; the loop updates Claim Progress and recomputes eligible actions. It does not rerun `legal_agent.run()` or the six-step Workflow. `FACT_PROVIDED` remains `human_asserted`, not independently verified.

Claim Progress is tracked per Claim as `UNTOUCHED`, `ATTEMPTED_UNRESOLVED`, or `COVERED`. `COVERED` means the bounded processing requirement for that Claim was handled; it does not mean an enterprise fact was independently verified.

## Bounds and Failure Behavior

The default Harness policy is at most 3 decision rounds, 2 targeted retrieval calls, 6000 characters of decision/evidence context per action, and 2 attempts per action/gap. Duplicate action/gap protection and a claim-scoped Human Fact guard prevent repeating already-consumed work or requesting the same fact indefinitely. Only a timeout or generic tool error may consume the one bounded retry; no-hit, invalid output, fallback, or failed relation stops without retry. Runtime clamps policy values to implementation limits. These are deterministic safety ceilings, not a monetary/token-cost guarantee. Trace records observed context characters and action latency; it does not claim actual model token or cost measurement.

No-hit, timeout, invalid output, relation failure, exhausted round/tool budget, or context-budget exhaustion stops the loop conservatively. The Legal Agent retains its normal output and the Dynamic workflow continues through its established Human Review policy; unresolved risk remains subject to Final Review. The loop itself does not invent evidence or approve a claim.

## Scope and Limitations

- The loop is enabled for Dynamic Runtime only. The fixed `/api/crisis/run` path keeps its existing behavior.
- Retrieval reuses the current local Legal RAG callable. It is not an arbitrary ToolRunner tool call and has no external side effect.
- Action eligibility, safety checks, and execution authority remain program-controlled. The Legal LLM is only asked to propose among multiple eligible actions; a single eligible action does not require a proposal call. The deterministic policy remains available for safe decisions and fallback. Tests use deterministic mock/fake callers.
- Event Fact Gap detection is independent of `risk_level`: a generic explicit-unknown marker plus a concrete unknown dimension can be recorded at any risk level. Risk, claim importance, statement relevance, coverage, and existing evidence belong to downstream handling policy, not gap existence.
- This boundary change does not add risk-weighted prioritization. Current P32 recommendations use the Claim requirement and observed relation/coverage/retrieval state; they do not claim a complete policy combining all business risk dimensions.
- In mock mode, this is a narrow deterministic offline heuristic, not general Chinese semantic understanding or a claim about production detection accuracy. It does not establish that event/news/user statements are true, and uses no case-specific keyword list.
- Human responses are observations, not independent verification. A supplied fact remains `human_asserted` and requires review.
- Checkpoint storage remains the existing JSON/single-process persistence model; this change does not provide cross-worker exactly-once execution.
- A bounded Legal action loop is not a general multi-round Agent framework, autonomous planning, or proof that a legal conclusion is correct.

## Context, Checkpoint, And Trace Boundaries

- ContextPack is the role-specific information used for the current Agent decision.
- Checkpoint keeps the complete run state and immutable ContextPack snapshots needed for pause/resume.
- Trace keeps only operational summaries by default: pack hash-derived id, role, character count, selected sections, fact/evidence counts, budget, truncation, and skill/tool execution metadata. Full event, draft, evidence text, history, rendered ContextPack, and Prompt bodies are not copied into Agent Trace.
- Mock Writer V1/V2 use the same domain-neutral cautious wording. They validate workflow/state/revision behavior only; their output is not evidence of semantic understanding or public-statement quality.
- Human Fact responses re-enter the same Legal loop as structured Observations; they do not restart the complete Legal Agent or outer Workflow.
