# CrisisAgent Interview Risk Points

## 1. RAG 指标怎么定义

面试时不要只说“RAG 效果变好了”，要拆成可解释指标：

- `topK hit rate`：Top-K 检索结果里是否包含期望来源或期望 source category。
- `context precision`：最终进入上下文的 evidence 中，source category 匹配当前问题领域的比例。
- `context pollution rate`：最终 evidence 中 wrong-category chunk 的比例，等于 `1 - context precision`。
- `fallback rate`：检索异常或后端不可用时进入 fallback 的比例。Gate skip 不是 fallback。

推荐回答：我会同时看召回和污染。Recall@K 高只能说明搜到了正确来源，但如果同时混入大量错误领域 chunk，Legal Agent 仍可能被污染，所以还要看 context precision、context pollution rate 和 fallback rate。

## 2. Rerank 是提准，不是提速

Reranker 发生在候选召回之后，目标是把更可靠、更匹配领域的 evidence 排到前面，并降低 wrong-category chunk 的权重。

它通常不会让系统更快，因为它多了一步排序计算。它解决的是 precision、source category match 和 context pollution 问题，不是 latency 问题。

推荐回答：在 CrisisAgent 里，Hybrid Retrieval 负责扩大候选池，Domain-Aware Reranker v2 负责降低跨领域污染。Frozen Retrieval Holdout v1 中 Recall@3 保持 0.90，Context Pollution 从 0.4722 降到 0.3222，这说明它主要提升的是证据质量，而不是检索速度。

## 3. RAG 质量差时如何安全降级

RAG evidence 不可靠时，不能假装“用了知识库就更可信”。项目通过 RAG Evidence Quality Gate 做轻量判断：

- evidence 为空：标记 `low_confidence`。
- retrieval fallback：标记 `fallback_used`。
- score 或 rerank_score 低：记录 `low_score` 或 `low_rerank_score`。
- source category 不匹配：计算 `context_precision` 和 `context_pollution_rate`。
- 污染率过高：建议触发 Human Review。

推荐回答：我不会让低质量 evidence 直接支撑法律结论。Quality Gate 会把 evidence 质量转成可审计信号；如果是 low confidence，就结合 Guardrail 和 Human Review 做安全降级，让人工审核看到“为什么这次证据不够稳”。

## 4. Agent-level failure vs Runtime-level failure

Agent-level failure 是某个 Agent 内部失败，例如 LLM timeout、invalid JSON、schema validation failed、retriever exception 或 fallback。

Runtime-level failure 是执行系统失败，例如任务队列提交失败、checkpoint 写入失败、resume 找不到 checkpoint、worker 异常或状态机非法流转。

推荐回答：这两类失败处理方式不同。Agent-level failure 要写入该 Agent trace，并决定是否 fallback 或进入 Human Review；Runtime-level failure 要写 checkpoint、更新 session 状态为 FAILED，并通过 readiness、metrics 和 audit log 排查。
