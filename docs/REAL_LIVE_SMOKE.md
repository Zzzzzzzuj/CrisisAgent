# Real Live Smoke

普通 Pytest、CI 和离线 demo 不访问真实网络。真实 live smoke 是授权环境下由开发者手动执行的一次验收，不是自动化测试，也不代表生产级监控能力。

## Preparation

1. 只使用公开、允许访问的 GDELT DOC 查询源，优先于需要 API key 的 NewsAPI。不要把 NewsAPI key 写入仓库或文档。
2. 在 data/source_registry.local.json 中登记一个 gdelt_doc source，并保持 source URL 为 HTTPS、enabled=true、max_items 不超过 3。
3. 创建一个 enabled Watchlist，配置公司/品牌名称和有限风险关键词。运行时使用 AGENT_MODE=mock、RUNTIME_MODE=sync，不调用真实 LLM。
4. 确认来源的 robots、授权范围、查询窗口和限速设置；本项目不绕过 robots、登录、验证码或反爬措施。

## Commands

PowerShell 示例：

    $env:ENABLE_API_LIVE_FETCH="true"
    $env:AGENT_MODE="mock"
    $env:RUNTIME_MODE="sync"
    uvicorn backend.main:app --reload

单次受控监测：

    python scripts/run_scheduled_live_monitor.py --once --provider gdelt_doc --live-fetch true

查看结果：GET /api/live-monitor/runs、GET /api/collected-items?provider=gdelt_doc、GET /api/alerts。

## Acceptance

- collected：请求成功并得到匹配公开信号；
- no_match：请求成功但没有匹配内容，不等于网络失败；
- failed：请求、配置或解析失败；
- skipped_by_robots：robots 检查不允许访问；
- 没有自动运行 Agent、创建声明或发布内容；automatic_publish=false。

Smoke 后只清理自己创建的 runtime JSON，不提交 data/source_registry.local.json、真实采集结果或密钥。通过标准是：来源受白名单约束、条目带 provider/entity metadata、结果可查询、失败状态可解释，并且没有自动发布动作。
