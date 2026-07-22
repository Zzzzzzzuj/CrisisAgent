# Evaluation System

## 目标

当前 evaluation 系统的目标不是做线上监控，而是做离线评测。

也就是：

- 给定一批危机场景
- 直接跑真实 workflow
- 看 Agent A 判断得对不对
- 看最终 scores 稳不稳
- 看整条链路有没有 fallback
- 看耗时分布怎么样

## 当前文件结构

评测模块在 `evaluation/` 下：

- `cases.json`
- `evaluator.py`
- `metrics.py`
- `outputs/`
- `reports/`

## cases.json 做什么

`cases.json` 是评测数据集。

每条 case 现在包含：

- `id`
- `event`
- `expected_risk`
- `expected_emotion`
- `expected_tone`
- `category`
- `tags`

这些字段让我们不只是能看“答没答对”，还能看：

- 哪类 case 容易错
- 哪种 tone 是否稳定
- 哪些标签下表现较差

## evaluator.py 做什么

`evaluator.py` 是评测执行器。

它会：

1. 读取 `cases.json`
2. 对每个 case 调用 `run_crisis_workflow`
3. 收集 workflow 结果
4. 调用 `metrics.py` 计算指标
5. 保存 JSON 报告
6. 生成 Markdown 报告

## metrics.py 做什么

`metrics.py` 把统计逻辑从 `evaluator.py` 里抽了出来，职责更清楚。

它负责：

- `accuracy` 计算
- `fallback` 统计
- `duration` 统计
- `agent_metrics`
- `category_metrics`

这样以后如果要加：

- tag 维度统计
- confusion matrix
- score 分布分析

都可以继续往这一层加，而不用把 `evaluator.py` 写得很重。

## 整个评测流程

文字流程图如下：

测试案例
 ↓
workflow
 ↓
收集：
- Agent A结果
- scores
- trace
 ↓
计算：
- risk_accuracy
- emotion_accuracy
- tone_accuracy
- fallback_rate
- latency
- agent_metrics
- category_metrics
 ↓
生成：
- JSON报告
- Markdown报告

## 当前收集的核心数据

每个 case 会收集：

- Agent A 输出
- 最终 `scores`
- 完整 `trace`
- `trace_duration_ms`
- `fallback_count`
- `fallback`

这意味着评测不仅能看“准不准”，还能看“慢不慢”“稳不稳”。

## 当前核心指标

### 全局指标

- `risk_accuracy`
- `emotion_accuracy`
- `tone_accuracy`
- `fallback_rate`
- `average_duration_ms`

### Agent 维度指标

每个 Agent 会统计：

- `average_duration_ms`
- `fallback_count`
- `fallback_rate`
- `total_runs`

### Category 维度指标

每个 category 会统计：

- `total_cases`
- `risk_accuracy`
- `emotion_accuracy`
- `tone_accuracy`
- `fallback_rate`
- `average_duration_ms`

## 输出报告

### JSON 报告

会保存到：

- `evaluation/outputs/evaluation-<timestamp>.json`

里面包含：

- summary
- case_results
- agent_a_output
- final_scores
- trace

这个版本适合程序处理和进一步分析。

### Markdown 报告

会保存到：

- `evaluation/reports/latest_report.md`

它适合人直接看，尤其适合：

- 自己复盘
- 面试展示
- 和别人讨论 case 表现

## 为什么这套 evaluation 有价值

因为现在这个项目已经不只是“能跑起来”，而是开始具备了工程闭环：

- workflow 能执行
- trace 能记录
- fallback 能观察
- evaluation 能量化
- report 能沉淀

这会让后面接真实 LLM、调 Prompt、接知识库时，改动不再是“拍脑袋”，而是可以被比较、被解释、被复盘。
