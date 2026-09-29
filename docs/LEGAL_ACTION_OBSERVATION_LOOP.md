# Legal Action / Observation Loop

This is a bounded Legal-stage control flow for Dynamic Runtime, not a new agent or a general planner. The fixed six-role workflow remains unchanged. The loop reuses the existing deterministic P32 Legal Action Policy, P33 claim-targeted retrieval, Claim Coverage, and Human Fact pause/resume path.

## Runtime Flow

```text
Legal Claim Extraction + current Relation/Coverage
  -> P32 recommends an action
  -> execute one bounded action
  -> update Relation/Coverage from the observation
  -> run P32 again against the updated state
  -> continue, request human facts, or stop
```

An observation can change the next action. For example, when a targeted legal search finds a relevant rule, the claim coverage changes to `candidate_found`; P32 no longer recommends searching that same gap, and the loop uses the available rule candidate or stops. If there are multiple distinct legal-rule gaps, the next retrieval is for the next claim and its record includes the preceding observation. The loop will not repeat retrieval for the same claim/gap after a no-hit or failure.

Case-fact gaps are not sent to Legal RAG. They produce `REQUEST_HUMAN_FACT`, after which the existing Dynamic Runtime checkpoint path waits for a human response. `FACT_PROVIDED` remains `human_asserted` and ends in final review. `FACT_UNAVAILABLE` becomes a new observation, permits one Writer V2 safety revision, and then either continues to Decision or stops for final review. Legal and earlier agents are not rerun.

## Bounds and Failure Behavior

The default Harness policy is at most 3 decision rounds, 2 targeted retrieval calls, 6000 characters of decision/evidence context per action, and 2 attempts per action/gap. Only a timeout or generic tool error may consume the one bounded retry; no-hit, invalid output, fallback, or failed relation stops without retry. Runtime clamps policy values to implementation limits. These are deterministic safety ceilings, not a monetary/token-cost guarantee. Trace records observed context characters and action latency; it does not claim actual model token or cost measurement.

No-hit, timeout, invalid output, relation failure, exhausted tool-call budget, or context-budget exhaustion stops the loop conservatively. The Legal Agent retains its normal output and the Dynamic workflow continues through its established Human Review policy; the loop itself does not invent evidence or approve a claim.

## Scope and Limitations

- The loop is enabled for Dynamic Runtime only. The fixed `/api/crisis/run` path keeps its existing behavior.
- Retrieval reuses the current local Legal RAG callable. It is not an arbitrary ToolRunner tool call and has no external side effect.
- The P32 action recommendation is deterministic. The LLM relation mode may be used only where the existing relation implementation is configured for it; tests use deterministic mock/fake callers.
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
- Human Fact observations affect Writer V2 and Final Review; they do not restart the complete Legal planning loop.
