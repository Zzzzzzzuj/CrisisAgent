# CrisisAgent Evaluation Methodology

本文档说明 CrisisAgent 当前测试和评测体系。它的目标不是证明系统已经生产上线，而是证明这个 AI Agent 原型的关键链路可运行、可观察、可复现，并且保留失败实验和边界说明。

## 1. Unit Tests

普通单元测试覆盖：

- Agent mock / LLM fallback schema
- LLM JSON parser 和字段校验
- Guardrail 规则
- RAG retriever / reranker / embedding readiness
- Checkpoint repository
- Auth / RBAC
- Observability metrics

运行：

```bash
python -m pytest tests -q
```

当前回归结果：

```text
447 passed
```

## 2. Runtime Tests

Runtime 测试覆盖：

- Planner / Plan Validator / Executor
- AgentState 状态流转
- Dynamic Runtime 执行顺序
- Checkpoint save/load/list/delete
- Resume after approve
- WAITING_HUMAN / COMPLETED / FAILED / REJECTED
- Async runtime queued / running / completed / failed

这些测试确保 Agent 之间不是直接互相调用，而是通过 `AgentState.results` 和 trace 传递状态。

## 3. RAG Gate Tests

Retrieval Need Gate 的目标是判断 Legal Agent 当前是否真的需要 crisis-response RAG。

测试覆盖：

- 当前危机事件应放行 RAG
- 培训、历史统计、模板写作、未来演练等非当前危机任务应跳过 RAG
- Challenge v1/v2/v3 的 frozen / post-hoc 结果被分别记录

重要边界：

- Gate v1 Challenge v1 first run = FAIL
- Gate v2 Challenge v2 first run = FAIL
- Gate v3 Challenge v3 first frozen holdout = PASS

Challenge v3 运行后不再是 untouched holdout。

## 4. Retrieval Holdout

Reranker v2 使用 frozen retrieval holdout 做单变量验证。

合法比较口径：

- Old Reranker vs Domain-Aware Reranker v2
- Candidate pool parity = true
- BGE / Hybrid / Top-K / threshold / KB 固定

结果：

- Recall@3: 0.90 -> 0.90
- Context Pollution: 0.4722 -> 0.3222
- Source Category Match: 0.4611 -> 0.6278
- Pollution Relative Reduction: 31.77%

这说明 Reranker v2 降低了跨领域上下文污染，但它仍是手写规则，不是训练模型。

## 5. Guardrail Tests

Guardrail 测试覆盖：

- Prompt injection
- 绝对承诺
- 未核实事实定性
- 直接承认违法
- 隐私信息泄露
- 跳过人工审核暗示

Guardrail 命中后不会自动改写 Agent 输出，而是触发 Human Review。

## 6. Reliability Tests

可靠性测试包括：

- LLM timeout fallback
- invalid JSON repair
- schema validation failed
- LLM fallback trace
- runner timeout / incremental report

真实 LLM smoke 使用 DeepSeek + BGE，结果为：

```text
PASS_WITH_LLM_FALLBACK_OBSERVED
```

含义是：真实请求链路跑通，但观察到 structured output 不稳定并触发 fallback。不能写成“所有 Agent 真实 LLM 稳定成功”。

## 7. RAG Ablation

`scripts/run_rag_ablation_demo.py` 用同一个危机事件对比：

- `RAG_ENABLED=false`
- `RAG_ENABLED=true`

输出：

- final_statement
- legal_risks
- safe_points
- guardrail_triggered
- evaluation scores
- rag_used
- retrieval_backend
- evidence_chunks count
- evidence_summary

这个 demo 用于面试解释“RAG 开启后 Legal Agent 多了哪些证据和合规依据”。它不是大规模统计实验。

## 8. E2E Regression

Final E2E Regression 覆盖：

- Fixed Workflow
- Dynamic Runtime
- Gate Skip
- Gate Hit
- Gate True + No Hit
- Retriever Exception / Fallback
- LLM Failure Fallback
- Human Gate
- Persistence
- Trace
- Frontend build

报告保留已知限制，包括 module-level state 的历史风险、Reranker 手写规则、Gate 仍有 FP/FN、真实网络稳定性未覆盖和当前没有完整 automatic retry。

## 9. What The Evaluation Does Not Prove

当前评测不能证明：

- 线上生产 SLA
- 大规模真实用户稳定性
- 所有 LLM 输出都稳定 JSON
- RAG 对所有领域泛化
- 分布式队列可靠性
- pgvector / ANN 检索效果

更准确的结论是：CrisisAgent 已经具备较完整的 AI Agent 工程化验证体系，适合作为 production-ready prototype 和面试展示项目。
