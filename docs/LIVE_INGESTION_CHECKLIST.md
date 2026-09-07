# Live Ingestion Checklist

本文档用于一次最小、手动确认的 live-fetch 验证。它不是全网爬虫方案，也不代表 CrisisAgent 已接入生产舆情数据。

## 1. 选择测试源

优先选择一个公开 RSS feed，而不是直接抓取网页。RSS 通常已经提供标题、链接、摘要和发布时间，抓取范围更容易限制，也更容易复现。

测试源应满足：

- 公开访问，不需要登录、订阅、验证码或授权；
- 使用 HTTPS；
- 来源方允许自动读取；
- 只代表一个明确的企业或主题；
- 你已人工确认其 robots.txt 和使用条款允许该用途；
- 不包含个人隐私、账号信息或需要特殊权限的内容。

不要使用任意搜索结果页、社交平台个人页面、需要登录的后台或未经确认的转载聚合页。本文不填写具体真实网址，URL 由操作者自行确认后放入本地文件。

## 2. 准备本地 Registry

复制示例文件，但不要修改并提交示例文件：

```powershell
Copy-Item data/source_registry.example.json data/source_registry.local.json
```

编辑 `data/source_registry.local.json`，只保留一个经确认的 source。将占位 URL 替换为你确认过的公开 RSS 或单篇文章 URL，并设置：

```json
{
  "source_id": "manual_safe_source",
  "source_name": "Manual Safe Source",
  "source_type": "rss",
  "url": "https://<manually-confirmed-host>/<feed-path>",
  "enabled": true,
  "company_keywords": ["<company-keyword>"],
  "risk_keywords": ["投诉", "监管"],
  "respect_robots": true,
  "rate_limit_seconds": 3,
  "timeout_seconds": 10,
  "max_items": 3
}
```

关键限制：

- `enabled=true` 只放在本地 Registry；
- `max_items` 设置为 `3`；
- `respect_robots` 保持 `true`；
- 只放一个 source；
- 不配置递归 URL 或站点首页；
- `data/source_registry.local.json` 已加入 `.gitignore`，不要提交。

示例 Registry `data/source_registry.example.json` 必须继续保持所有 source `enabled=false`。

## 3. 运行前检查

先确认 Python 虚拟环境已激活，并确认没有设置真实 LLM 运行模式。live-fetch 只验证采集和 ingestion，不调用真实 LLM：

```powershell
$env:AGENT_MODE="mock"
$env:RUNTIME_MODE="sync"
$env:CHECKPOINT_STORAGE="json"
```

不需要启动 PostgreSQL、Redis 或前端，也不需要运行 Workflow。

## 4. 运行 live demo

先运行默认安全模式：

```powershell
python scripts/run_live_ingestion_demo.py --source-registry data/source_registry.local.json
```

没有 `--live-fetch` 时不得访问网络，只会输出 live fetch disabled 提示。

确认 Registry、robots 和测试源都经过人工检查后，才运行一次：

```powershell
python scripts/run_live_ingestion_demo.py `
  --live-fetch `
  --source-registry data/source_registry.local.json
```

该命令只读取 Registry 中 `enabled=true` 的 source。它不会递归抓取、不会扩展站内链接、不会调用 LLM，也不会自动发布声明。

## 5. 解释 FetchResult

输出状态的含义：

- `collected`：请求和解析成功，并且有条目命中公司或风险关键词；
- `no_match`：请求成功，但没有条目命中关键词；这不是网络失败；
- `failed`：HTTP、超时、解析或正文提取失败；不能解释成“没有舆情”；
- `skipped_by_robots`：robots.txt 禁止，或 robots 检查失败时采取保守跳过；
- `disabled`：source 没有启用，因此没有采集。

尤其要区分：

```text
no_match = 成功访问，但没有发现符合筛选条件的内容
failed = 采集过程失败，无法确认有没有符合条件的内容
```

只有 `collected` 的 items 会继续进入 normalize、deduplicate、cluster 和 risk analyze。真实来源默认是 `unverified`；如果出现高风险、历史不确定、事实未证实或来源冲突，仍然应进入 Human Review，而不是自动发布。

## 6. 普通测试为何不联网

普通 pytest 使用本地 RSS/XML/HTML sample、fake robots checker 和 mock adapter，不调用真实网络。默认 pipeline 仍使用本地 JSON/CSV；live adapter 只有显式 `--live-fetch` 才会执行。

验证离线路径：

```powershell
python -m pytest tests -q
```

完成验证后删除或保留本地 `data/source_registry.local.json` 均可，但它不会被 Git 跟踪。不要把真实 URL、响应原文或运行产物写入 `data/source_registry.example.json`。

## 7. 本次验证边界

一次成功的 live-fetch 只能证明：

```text
一个人工确认的 source
→ FetchResult
→ RawSentimentItem
→ 现有 ingestion pipeline
```

它不能证明实时全网监控、长期稳定性、生产 SLA、事实真实性或自动发布安全性。
