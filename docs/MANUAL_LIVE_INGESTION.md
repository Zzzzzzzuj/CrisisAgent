# 手动联网采集

> 除 RSS/article URL 外，P17 支持手动启用的 GDELT DOC 与 NewsAPI 查询源。所有来源仍必须经过 Source Registry、服务器开关和人工确认；详见 [Live News Ingestion](LIVE_NEWS_INGESTION.md)。

## 1. 为什么需要手动入口

白名单 RSS / 单篇文章采集可以验证真实 ingestion 链路，但联网行为具有外部副作用，不能因为用户打开工作台就自动执行。因此 API 默认关闭 live-fetch，只有服务端配置和用户确认同时满足时才允许运行。

## 2. 服务端开关

默认值：

```text
ENABLE_API_LIVE_FETCH=false
```

本地授权测试时可以在启动后端的 PowerShell 中设置：

```powershell
$env:ENABLE_API_LIVE_FETCH="true"
python -m uvicorn backend.main:app --reload
```

只有 `live_fetch=true`、`dry_run=false` 且服务端开关为 true 时，API 才调用已有 live adapter。`live_fetch=false` 和 `dry_run=true` 始终不访问网络。

## 3. 准备安全来源

使用未提交的 `data/source_registry.local.json` 或 Source Registry API 配置来源：

- source type 只能是 `rss` 或 `article_url`；
- URL 必须是 HTTPS；
- source 必须明确 `enabled=true`；
- 只配置自己有权访问的公开来源；
- 建议优先 RSS；
- 将 `max_items` 限制为不超过 3；
- 保留 robots、timeout 和 rate limit 配置。

示例只用于说明字段，不能替代对实际来源的授权确认：

```json
{
  "source_id": "safe_rss_source",
  "source_type": "rss",
  "url": "https://<approved-domain>/feed.xml",
  "enabled": true,
  "max_items": 3,
  "respect_robots": true
}
```

## 4. 从 Workbench 运行

打开 `/workbench`，展开“高级：手动联网采集”，阅读提示并输入完整确认文本：

```text
我确认手动联网采集
```

点击“手动联网采集 enabled 来源”。页面会显示 `run_id`、run status、每个 source result、失败原因和 cluster 数量。即使服务端返回 403，也表示本次没有联网。

## 5. Source result 状态

- `collected`：已抓取并得到匹配 item；
- `no_match`：请求正常完成，但没有匹配公司或风险关键词的 item；
- `failed`：抓取或解析过程失败；
- `skipped_by_robots`：robots.txt 不允许访问；
- `disabled`：来源未启用或本次是非 live 运行。

`failed` 不等于“没有舆情”，应结合 `failed_reason` 排查网络、解析或配置问题；`no_match` 才表示本次成功处理但没有匹配结果。

## 6. 安全边界

系统不支持任意 URL 直接采集、域名递归、站内深度爬取、登录论坛、验证码处理、反爬绕过、代理池或个人隐私采集。真实采集仍受白名单、HTTPS、robots、timeout、rate limit 和 max_items 约束，也不会自动发布声明。

普通 pytest 不访问真实网络，测试只使用 fake adapter、本地 sample feed 和 HTML fixture。`data/source_registry.local.json` 不应提交到 Git，示例 registry 保持 `enabled=false`。

## 7. 面试讲解版

我没有把系统做成全网爬虫，而是增加了一个受保护的手动联网入口。它需要服务端显式开关、白名单 enabled source 和用户二次确认，采集层继续遵守 robots、超时、限速和数量上限。默认 Demo 仍然离线，真实采集只作为授权环境下的低频验证能力。
