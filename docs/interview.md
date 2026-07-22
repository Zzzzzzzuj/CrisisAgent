# Interview Notes

## 项目介绍（1分钟版本）

CrisisAgent 是一个面向企业危机公关场景的多 Agent 后端系统。它接收一段危机事件描述，然后通过固定 workflow 串联多个角色：先做舆情分析，再生成第一版声明，再做红队攻击和合规审查，再修订文案，最后输出最终声明和评分。项目用 FastAPI 做接口层，用 Python 做 workflow 编排，支持 mock 和 llm 双模式，还有 trace 和离线 evaluation，方便观察每一步的输出、耗时和 fallback 情况。

## 为什么拆多个 Agent？

因为危机公关不是一个单一任务，它至少包含几个不同能力：判断风险、写文案、舆论挑刺、法务审查、最终拍板。把它们拆开之后，每一步的职责更清楚，也更容易调试。比如如果最后文案不稳，我可以快速判断是 Agent A 的风险识别问题，还是 Agent D 没有挑出关键舆论风险。

## 为什么不用一个 LLM？

一个 LLM 当然也能一把梭生成结果，但工程上会比较黑盒。你很难知道它到底是判断错了、措辞错了，还是法务思路错了。多 Agent 的好处是把复杂任务拆成可观测的子步骤，这样更容易做 Prompt 调优、做 fallback、做评测，也更容易后续接不同能力，比如法务知识库。

## workflow 怎么设计？

我把 workflow 设计成单独的编排层，放在 `backend/workflow.py`，它是唯一流程入口。顺序是固定的：Agent A 舆情分析，Agent C 第一版文案，Agent D 红队攻击，Agent B 合规审查，Agent C 第二版文案，最后 Agent E 做最终决策。这样 API 层很薄，Agent 层也不会互相缠绕。

## Agent 之间怎么通信？

通信方式很简单，都是 workflow 显式拼 payload。每个 Agent 接一个 `str` 或 `dict`，返回一个结构化 `dict`。比如 Agent A 输出 `sentiment_analysis`，然后 workflow 再把它放进 Agent C 第一版的输入里。这样数据流是透明的，trace 也更容易记录。

## 为什么需要 fallback？

因为只要接了真实 LLM，就一定会遇到网络问题、超时、JSON 解析失败、字段缺失这些情况。如果没有 fallback，整个 workflow 会很脆。现在我的设计是：Agent 在 llm 模式失败时自动退回 mock 逻辑，这样 API 结构不变，workflow 不会崩，trace 里还能明确看到哪一步 fallback 了。

## LLM 输出格式怎么保证？

我做了三层保证。第一层是 Prompt 约束，要求模型返回固定 JSON。第二层是统一的 `json_parser`，处理 code fence、额外解释文字之类的脏输出。第三层是 Agent 内部字段校验和 normalize，确保最终返回结构稳定。如果解析失败或字段不对，就直接 fallback 到 mock。

## 为什么需要 trace？

trace 是这个项目工程化很关键的一层。它不仅记录每一步的 input 和 output，还记录 start_time、end_time、mode、status、fallback。这样我可以知道哪一步最慢、哪一步经常 fallback、某个 case 是从哪一步开始偏的。没有 trace，整个系统虽然能跑，但很难维护。

## evaluation 怎么做？

我单独做了 `evaluation/` 模块，不走 API，直接调用真实 workflow。评测数据集放在 `cases.json`，执行逻辑在 `evaluator.py`，统计逻辑抽到 `metrics.py`。现在能统计 risk、emotion、tone 的 accuracy，也能统计 fallback rate、平均耗时、按 Agent 和按 category 的指标。最后还会产出 JSON 和 Markdown 报告。

## 为什么 Agent B 适合接 RAG？

因为 Agent B 本质上是在做合规和法律风险审查，这类任务天然依赖外部知识。比如监管规则、行业规范、历史公关案例、公司内部法务口径，这些都不是单靠模型参数就能稳定覆盖的。把 RAG 接到 Agent B 上，价值会比接到其他 Agent 更直接，因为它的输出本来就和“依据什么规则判断”强相关。

## 项目最大的难点是什么？

我觉得不是把接口跑起来，而是让整个系统“稳定且可解释”。多 Agent 项目很容易变成一堆 prompt 拼起来的 demo，但真正难的是：输出结构要稳定、失败要能兜底、trace 要能看、evaluation 要能量化。换句话说，最大的难点是把一个能跑的 Agent demo，做成一个后续可以持续演进的工程骨架。
