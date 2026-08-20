# Long-form Generation Strategy

CrisisAgent should not generate long crisis documents by putting everything into one prompt and hoping the model stays consistent.

## Recommended Flow

1. Build an outline.
2. Split the task into sections.
3. Generate each section with shared context.
4. Run consistency checks across sections.
5. Merge the final document.
6. Apply guardrails.
7. Send high-risk output to Human Review.

## Why Not One Giant Prompt

One-shot long generation is fragile because:

- context may exceed model limits
- facts can drift between sections
- legal wording may become inconsistent
- citations or RAG evidence may be used unevenly
- guardrail issues may only appear in later paragraphs

## Session State

For multi-turn drafting, the system should reuse:

- original crisis event
- selected reasoning mode
- Legal RAG evidence
- previous final statement
- evaluation scores
- guardrail results
- reviewer comments

This keeps follow-up edits grounded in the same session rather than treating each question as a new isolated prompt.

## Optional SSE Streaming

SSE can stream progress such as:

- outline generated
- section drafted
- consistency check completed
- guardrail check completed
- waiting for human review

For high-risk content, the final statement should still be validated before publishing. Streaming is a UX mechanism, not a replacement for compliance checks.
