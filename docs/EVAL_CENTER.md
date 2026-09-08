# Eval Center

## 为什么需要 Eval Center

Agent、RAG、MCP 和工具调用本身不证明系统可靠。CrisisAgent 的 Eval Center 将已有
运行记录和确定性规则整理为可保存的 `EvalRun`，让每次变更后都能检查产品闭环是否
退化，而不是只展示一条成功的 demo。

第一版只做离线评估：不访问网络、不调用真实 LLM、不重新采集、不重跑 Agent，
也不自动发布任何声明。

## 与既有评估的关系

- RAG retrieval eval：验证检索来源、Recall@K、污染率和回归基线；
- Evidence Quality Gate：在实际 Legal RAG 运行中判断证据可信度；
- Tool Reliability Evaluation：用 deterministic fake tools 验证 timeout、retry、fallback、loop detection；
- Eval Center：将 ingestion、事件、态势评分、Agent Run、报告安全边界和 Tool Reliability 汇总成可查询的 EvalRun。

Eval Center 不替代 RAG 专项评测，也不把一次 EvalRun 伪装成 LLM 输出质量评测。

## 六类离线维度

| 维度 | 校验内容 |
| --- | --- |
| ingestion | `source_results`、状态可识别、`no_match` 不作为失败、默认 live-fetch 关闭 |
| event | 来源、风险、事实、事件状态和人工审核字段是否保留；归档事件不进入 Top Urgent |
| urgency | 高风险/事实冲突分级、历史/完成/归档降级、`waiting_human` 加权 |
| agent_run | session、trace、声明草稿、`automatic_publish=false`、高风险审核保留 |
| report | 基于已有 run、无 live-fetch、无真实 LLM 调用、声明草稿措辞与未发布边界 |
| tool | 复用已有 deterministic fake-tool reliability suite 的成功率、超时、fallback、循环检测和审核触发指标 |

没有某类 runtime 记录时，Eval Center 会标记“当前无记录可检查”，而不是把“尚未运行”误判为产品失败。

## API

```text
POST /api/evals/run
GET  /api/evals/runs
GET  /api/evals/runs/{eval_run_id}
GET  /api/evals/overview
GET  /api/evals/regression
```

运行全部维度：

```json
POST /api/evals/run
{}
```

仅检查紧急度规则且不保存：

```json
POST /api/evals/run
{
  "dimensions": ["urgency"],
  "dry_run": true
}
```

`data/eval_runs.runtime.json` 保存 EvalRun 历史，可通过 `EVAL_RUN_STORE_PATH`
指定测试用临时路径；默认运行文件已被 `.gitignore` 忽略。

`GET /api/evals/regression` 比较最近两次保存的 EvalRun，返回通过率变化、新增失败用例和恢复用例。只有一条或没有历史记录时返回 `not_enough_runs=true`。

## 为什么第一版不用 LLM-as-judge

当前优先验证可确定、可复现的工程不变量。LLM-as-judge 本身会引入模型版本、提示词、采样和成本变量，适合后续用于人工标注补充，而不适合替代本项目的基础回归门槛。

## 当前边界和后续

- EvalRun 基于 JSON runtime store，适合本地 MVP，不是生产数据库；
- Report Eval 校验的是现有报告生成器的安全输出契约，不等同于对真实 LLM 文本做事实正确性判定；
- Tool Eval 当前直接复用离线 fake-tool suite，不会触发真实工具；
- 后续可补 golden cases、LLM-as-judge、pairwise prompt comparison、CI 自动 eval、人工抽检和持久化 regression dashboard。

## 面试讲解

> 我没有把“接上 Agent、RAG 和 MCP”当作项目完成。系统中每个关键层都有不同的评估口径：检索有 retrieval eval 和 evidence gate，工具有 timeout/retry/fallback/loop 的可靠性套件，产品工作台新增 Eval Center 后，会把 ingestion、事件元数据、紧急度、Agent Run、报告安全边界和工具指标保存为 EvalRun，并比较最近两次结果。第一版只跑确定性离线评估，不用 LLM-as-judge，目的是先把工程回归做成可复现的底线。
