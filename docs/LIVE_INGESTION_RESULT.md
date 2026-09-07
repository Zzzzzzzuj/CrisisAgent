# Live Ingestion Result

## 1. 验证目标

本次验证用于确认 CrisisAgent 的第一版白名单真实舆情采集入口能够：

```text
公开白名单 RSS
→ FetchResult
→ RawSentimentItem
→ normalize / deduplicate / cluster
→ risk analyze
→ ClusteredCrisisEvent
```

本次只验证 ingestion 链路，不验证真实 LLM、自动声明生成或生产环境运行。

## 2. 为什么使用白名单 RSS

RSS 已经提供标题、链接、摘要和发布时间，采集范围比任意网页搜索更容易限制，也更适合低频、可复现的手动验证。本次使用的 source 是提前登记的公开 RSS：

```text
source_id: cis_advisories_rss
```

采集过程仍遵守 Registry、robots、超时、条数和限速约束，不做全网发现、递归抓取、登录或反爬绕过。

## 3. 执行命令

先执行默认安全模式：

```powershell
python scripts/run_live_ingestion_demo.py --source-registry data/source_registry.local.json
```

输出：

```text
Live fetch is disabled. Re-run with --live-fetch to access allowlisted sources.
```

再由人工确认 source 后显式开启 live-fetch：

```powershell
python scripts/run_live_ingestion_demo.py `
  --live-fetch `
  --source-registry data/source_registry.local.json
```

`data/source_registry.local.json` 仅作为本地配置使用，不提交到 Git。

## 4. 输出摘要

```text
live_fetch = true
source_id = cis_advisories_rss
status = collected
fetched_count = 3
matched_count = 3
failed_reason = null
cluster_count = 3
automatic_publish = false
```

采集到的条目为：

1. `Multiple Vulnerabilities in Google Chrome Could Allow for Arbitrary Code Execution`
2. `Multiple Vulnerabilities in SonicWall SMA1000 Series Appliances Could Allow for Remote Code Execution`
3. `Multiple Vulnerabilities in PaperCut Products Could Allow for Remote Code Execution`

每条内容形成独立事件簇，结果状态为：

```text
event_status = uncertain
fact_status = unverified
risk_level = low
human_review_required = true
```

## 5. 本次验证通过的能力

- 默认不带 `--live-fetch` 时不会访问网络；
- Registry 中已启用的 RSS source 可以被正确读取；
- RSS 条目可以转换成 `RawSentimentItem`；
- 3 条 RSS 条目均通过关键词匹配；
- 采集结果成功进入现有 normalize、deduplicate、cluster 和 risk analyze 流程；
- 3 条内容被聚合为 3 个 `ClusteredCrisisEvent`；
- 未调用真实 LLM；
- 没有自动发布声明；
- 采集链路没有修改现有 Workflow、Agent、Prompt、RAG 或 API。

## 6. 为什么 risk_level=low 仍然需要人工审核

`risk_level` 和 `human_review_required` 表达的是不同维度：

- `risk_level=low`：当前规则没有识别出高危事件关键词；
- `event_status=uncertain`：无法确认这些内容是否对应当前正在发生的企业事件；
- `fact_status=unverified`：采集到的公开内容还没有经过业务事实核验。

当前 ingestion 规则只要发现事实未证实或事件状态不确定，就建议人工审核。因此：

```text
risk_level=low
并不等于
可以自动进入声明发布流程
```

这是保守的危机响应策略，避免把公开安全公告直接误当成已经确认的企业危机，也避免在事实不完整时自动生成对外结论。

## 7. 为什么 automatic_publish=false 很重要

本项目的 live-fetch 只负责采集和结构化分析，不负责对外发布。`automatic_publish=false` 明确表示：

- 采集结果不会自动生成并发送公开声明；
- 事实不确定时不会绕过 Human Review；
- 后续即使接入 Agent Workflow，也仍需经过现有审核和审批流程；
- 本次运行不会产生对外业务副作用。

## 8. 当前边界

- 本次验证的是一条公开白名单 RSS 的真实采集链路，不是完整的企业生产舆情监控；
- 测试源是公开安全公告 RSS，不是企业内部舆情平台或内部数据源；
- 本次未执行自动发布；
- 本次未调用真实 LLM；
- 本次没有验证长期定时调度、断点恢复、生产 SLA 或多来源持续监控；
- 本次结果不能说明系统已经具备全网爬虫能力；
- `data/source_registry.local.json` 是本地配置，不属于提交内容。

## 9. 面试讲解版

> 我为 CrisisAgent 增加了一版小范围真实采集能力，但没有做全网爬虫。本次选择了一个公开白名单 RSS，先在 Registry 中登记并人工确认，然后通过 `--live-fetch` 显式开启。3 条 RSS 条目成功转换为 `RawSentimentItem`，经过现有的规范化、去重、事件聚类和风险分析，最终形成 3 个事件簇。
>
> 这次结果里 `risk_level` 是 low，但 `human_review_required` 仍然是 true，因为 risk level 只表示当前规则识别出的风险强度，而 `event_status=uncertain`、`fact_status=unverified` 表示事实和事件时效都没有确认。对于企业危机系统，我宁愿把不确定信息交给人工审核，也不让采集到的公开内容直接触发自动发布。
>
> 这次验证证明的是白名单 RSS 能进入现有 ingestion pipeline，不代表已经实现全网舆情监控，也不代表接入了企业生产数据。真实 LLM、自动发布和生产调度都没有在本次验证中执行。
