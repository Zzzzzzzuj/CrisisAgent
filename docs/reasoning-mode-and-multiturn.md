# Reasoning Mode and Multi-turn Follow-up

Phase 17 adds a lightweight reasoning-mode selector and a session-based follow-up API. It does not change the existing agent workflow or prompt semantics.

## Reasoning Modes

The selector lives in:

```text
backend/core/reasoning_mode.py
```

Supported modes:

- `fast`: low-risk cases with no RAG evidence requirement. It keeps review lightweight and remains policy-based.
- `standard`: normal multi-agent crisis workflow with gate-controlled Legal RAG and guardrails.
- `strict`: high-risk or safety-sensitive cases. It recommends Legal RAG verification, required guardrails and Human Review.

## Selection Signals

The selector uses only runtime metadata and trace signals:

- `risk_level`
- `guardrail_triggered`
- `rag_confidence`
- `evidence_chunks_count`
- `llm_fallback_used`
- `user_requested_strict_review`

It writes:

- `selected_reasoning_mode`
- `reasoning_mode_reason`
- `recommended_execution_policy`

These fields are metadata and planning hints. The current phase does not reorder agents or remove existing workflow steps.

## Dynamic Runtime Integration

Dynamic Runtime records reasoning mode during state initialization and updates it again after execution when guardrail, RAG and LLM trace metadata are available.

The response can include:

```json
{
  "selected_reasoning_mode": "strict",
  "reasoning_mode_reason": ["high_risk"],
  "recommended_execution_policy": {
    "review_depth": "strict",
    "legal_rag": "force_or_verify",
    "guardrails": "required",
    "human_review": "required"
  }
}
```

## Multi-turn Follow-up

Endpoint:

```text
POST /api/dynamic/{session_id}/followup
```

Request:

```json
{
  "question": "如果媒体追问下一步怎么办？",
  "followup_type": "media_qna"
}
```

Supported `followup_type`:

- `clarification`
- `rewrite`
- `media_qna`
- `internal_action`
- `regulator_response`

The follow-up response uses existing session state:

- original event
- final statement
- scores
- agent trace
- RAG evidence
- guardrail metadata
- approval state

It defaults to mock/offline generation and does not consume a real LLM.

## Why This Is Not a New Agent Workflow

Reasoning mode currently provides policy hints and explainability. It does not replace Planner, Executor, Legal RAG, Guardrails or Human Review.

Follow-up is also deliberately lightweight. It is a session-state Q&A layer, not a new autonomous agent loop.

## SSE and Streaming

SSE is useful when the user needs incremental text display, such as a long statement draft. It is less useful for tasks that require complete validation before display, such as:

- legal review
- guardrail decision
- approval/rejection
- final compliance-sensitive statements

For high-risk crisis content, streaming partial unreviewed text can create safety and audit problems. A safer approach is to stream progress events while keeping final text gated by validation and Human Review.
