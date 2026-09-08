# Eval CI Gate And Golden Cases

## 目的

Eval Center 将已有运行记录和确定性规则汇总为 `EvalRun`；Golden Cases 再补一组虚构、离线的危机响应安全预期。两者通过命令行脚本进入 CI，确保工程改动不会悄然降低既有检查的通过率。

这不是 LLM-as-judge，也不是线上效果指标。第一版不访问网络、不调用真实 LLM、不重跑 Agent、不触发 live-fetch，也不会自动发布声明。

## Golden Cases

[`data/eval_golden_cases.json`](../data/eval_golden_cases.json) 包含食品安全、隐私、产品质量、服务中断、虚假宣传、劳动争议、历史新闻和来源冲突等虚构场景。每条用例保存预期风险、事实/事件状态、人工审核要求、最低严重度、禁止表述和回应要素。

`golden_case` 维度只检查数据与安全规则：字段枚举是否合法、`forbidden_claims` 和 `required_response_features` 是否非空、高风险及事实冲突用例是否要求 Human Review，以及历史事件是否没有被预期为 `SEV-1`。它是回归基准的结构性安全检查，不代表模型已经生成了这些文本。

## 命令行

```powershell
python scripts/run_eval_center.py --pretty --min-pass-rate 0.8
python scripts/run_eval_center.py --dimensions golden_case,urgency --pretty
python scripts/run_eval_center.py --output data/eval_report.json --min-pass-rate 0.8
python scripts/run_eval_center.py --fail-on-regression --min-pass-rate 0.8
```

脚本默认以 dry-run 方式生成候选 `EvalRun`，不新增持久化历史。若已有历史 EvalRun，会将候选结果与最近一次历史结果比较：通过率下降或出现新增失败项时，`--fail-on-regression` 返回非零退出码。低于 `--min-pass-rate` 也会返回非零退出码。

`data/eval_report.json` 是本地 CI 产物，已由 `.gitignore` 忽略。

## CI

[`.github/workflows/eval.yml`](../.github/workflows/eval.yml) 在 push 和 pull request 时使用 Python 3.11，设置 mock/json/sync/hash/json-vector 的离线环境变量，执行完整 pytest 后运行 Eval CI Gate。它不启动 PostgreSQL、Redis、RQ 或 Docker，也不请求模型、embedding 下载或外部采集源。

## 后续边界

后续可在独立、人工审核过的数据基础上增加真实输出评分、prompt pairwise comparison、LLM-as-judge、人工抽检和 PR 评估报告评论；这些能力不属于当前确定性离线 Gate。

## 面试讲解

> 我没有把一次成功 demo 当作质量证明。项目先把 ingestion、事件、紧急度、Agent Run、报告和 ToolRunner 做成离线 EvalRun；P11 再加入虚构 Golden Cases 和 CLI Gate。CI 只运行确定性检查，低于通过率阈值或相对历史产生回归就失败。它不替代真实模型效果评测，但能防止工程改动破坏已有的审核、安全和数据契约。
