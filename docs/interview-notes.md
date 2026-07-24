# Interview Notes

## 1 分钟项目介绍

CrisisAgent 是一个企业危机公关决策系统。我没有把它做成单次 LLM 生成工具，而是做成了一个多 Agent Runtime。系统会先分析舆情，再生成回应草稿，然后做红队攻击、合规审查、二次修订和最终决策。后面我又扩展了 Dynamic Runtime，包括 Planner、Executor、AgentState、Human Gate、Checkpoint Resume 和 Dashboard，所以它不仅能生成结果，还能解释每一步怎么执行、哪里失败、是否需要人工审核，以及如何恢复。

## 3 分钟架构介绍

项目分两条线。

第一条是固定 workflow，顺序是 Agent A 舆情分析、Agent C 第一版文案、Agent D 红队攻击、Agent B 合规审查、Agent C 第二版文案、Agent E 最终决策。这个链路适合展示多 Agent 协作和 trace。

第二条是 Dynamic Runtime。用户输入事件后，Planner 根据事件类型和风险等级生成 plan，Plan Validator 自动补齐依赖并修正顺序，Executor 根据 plan 执行 Agent。所有中间结果写进 AgentState，Agent 之间不直接互相调用，而是通过状态传递。RuntimeEvaluator 和 Policy 判断是否需要 Human Gate，高风险任务会进入 WAITING_HUMAN。状态会保存到 checkpoint，人工 approve 后可以 resume。

同时系统有 RAG、Memory、Tool Calling、Context Engineering 和 Evaluation。RAG 主要用于 Agent B 合规审查，Memory 用于让 Writer Agent 参考历史危机经验，Tool Calling 用于给 Agent 扩展外部能力，Evaluation 用于离线评估风险识别、RAG 召回、Memory 命中和最终声明质量。最后用 Vue Dashboard 展示 session、trace、metrics 和人工审核。

## 为什么多 Agent？

因为危机公关不是一个单点生成问题，而是一个多角色协作问题。舆情、文案、红队、法务、最终决策关注点不同。如果用一个 LLM 全部做完，Prompt 会很复杂，错误也很难定位。拆成多个 Agent 后，每一步的输入输出都清楚，可以单测、替换、评估和观察。

## 为什么不用单 LLM？

单 LLM 可以做 demo，但工程上不稳定。比如最终声明有问题时，你不知道是舆情判断错了、红队没发现问题，还是合规审查没做好。CrisisAgent 把链路拆开后，每一步都有 trace 和评分，能定位问题，也方便后续把某个 Agent 单独升级为更强模型或接 RAG。

## Agent 之间怎么通信？

Agent 不直接调用其他 Agent。固定 workflow 里由 `workflow.py` 显式传递 dict。Dynamic Runtime 里由 `AgentState` 保存中间结果，再由 `adapter.py` 为每个 Agent 构造输入。这样 Agent 本身保持简单，编排逻辑集中在 runtime。

## LLM 失败怎么处理？

每个 Agent 都有 mock/llm 双模式。LLM 路径会经过 Prompt Loader、LLM Client、JSON Parser、字段校验和 normalize。如果调用失败、超时、JSON 解析失败或字段缺失，就 fallback 到 mock。这样不会因为单个模型错误导致整个 workflow 崩溃。

## 为什么 RAG 放 Agent B？

Agent B 是合规审查 Agent，最适合接 RAG。因为合规审查需要参考稳定知识，比如食品安全规则、危机回应规范、法律风险表达规则。如果让 Writer 直接编法律建议，容易幻觉；把 RAG 放到 Legal Agent，可以让法律风险判断更可控。

## 为什么需要 Memory？

RAG 解决的是外部知识，比如规范和法律表达规则。Memory 解决的是企业历史经验，比如过去类似危机中哪些策略有效、哪些表达踩过坑。两者不是一回事：RAG 偏知识库，Memory 偏经验库。

## 为什么需要 Human Gate？

企业危机公关是高风险场景，不能完全自动发布。系统可以生成建议，但高风险事件或质量评分低时，需要人工审核。Human Gate 让系统在自动化和安全控制之间取得平衡。

## 为什么需要 Checkpoint Resume？

Human Gate 会让 runtime 暂停，如果状态只在内存里，服务重启或等待时间长就会丢失上下文。Checkpoint 保存完整 AgentState，approve 后可以从原 session 恢复，而不是重新跑一遍。

## 怎么评估效果？

项目有 evaluation 模块。它读取 cases，调用真实 workflow/runtime，统计 risk accuracy、emotion accuracy、tone accuracy、RAG recall@k、MRR、memory hit rate、response quality 和 hallucination risk，并生成 JSON 和 Markdown 报告。这样不是凭感觉判断 Agent 好坏，而是用离线指标持续验证。

## 项目最大的难点是什么？

最大难点不是写某个 Agent，而是保持系统边界稳定。Agent 要能替换，workflow 不能被频繁打破；LLM 输出不稳定，所以要有 JSON Parser、normalize 和 fallback；动态 runtime 要支持人工审核和恢复，所以 AgentState 必须设计清楚。这个项目的重点是把 AI 能力放进一个可维护的工程系统里。

## 如何继续优化？

可以从四个方向优化：

- RAG: 接入真实 embedding 模型和向量数据库，增加 cross-encoder reranker。
- Agent: 将 Planner、Legal、Decision 逐步升级为更强 LLM。
- Evaluation: 引入更严格的 LLM-as-Judge 和人工标注集。
- Production: 增加数据库、权限、审计日志、异步任务队列和部署监控。
