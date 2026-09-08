# CrisisAgent 前端工作台

## 1. 目标

P6 新增 `/workbench` 页面，把 P1-P5 的后端 API 串成一条可操作的本地 Demo 流程：来源管理、采集运行、事件沉淀、运行 Agent、查看 Trace/Review 和查看报告。

## 2. 页面功能

- 数据源管理：新增 RSS 或单篇文章白名单来源、启用/禁用和配置检查；
- 采集运行：执行 dry-run 或默认 `live_fetch=false` 的离线 run；
- 危机事件：查看事件列表，并从 run cluster 创建 CrisisEvent；
- 事件控制台：查看事件风险与来源，使用默认 mock 模式运行 Agent；
- Trace / Review：查看 Agent 顺序、输出摘要、审核原因和允许动作；
- Report：查看已有 AgentRun 生成的 Markdown 报告。

## 3. 推荐流程

```text
打开 /workbench
  -> 添加或检查白名单来源
  -> 运行 dry-run / 离线 ingestion run
  -> 选择 run 中的 cluster 创建 CrisisEvent
  -> 选择事件并运行 Agent（mock）
  -> 查看 session、Trace 和 Human Review
  -> 查看 Markdown 声明草稿报告
```

工作台不提供 `live_fetch=true` 操作按钮，也不会自动发布声明。真实采集仍需要受控脚本显式开启，报告中的内容始终是声明草稿。

## 4. 与 P1-P5 API 的关系

前端只增加 API 封装和展示，不改变后端请求语义：

- P1：`/api/sources`；
- P2：`/api/ingestion/run` 和 runs 查询；
- P3：`/api/events`；
- P4：事件 Agent Run、Trace 和 Review；
- P5：事件 JSON / Markdown Report。

## 5. 当前边界

- 没有复杂登录页面；
- 没有真实企业数据接入；
- 没有默认联网采集；
- 没有 ECharts 大屏；
- 没有 PDF 下载；
- 没有自动发布能力；
- API 错误、空列表和报告未生成状态会在页面中提示。

## 6. 后续方向

后续可以增加 ECharts 风险趋势、来源健康度、事件历史和 Report 下载，但应继续复用现有 API 和 Human Review 边界，而不是在前端绕过审核流程。

## 7. 面试讲解版

我没有先做复杂的大屏，而是先做了一个最小工作台，把已有后端能力串成业务人员可以理解的流程。用户可以管理白名单来源、运行离线采集、把 cluster 沉淀为 CrisisEvent，再运行 mock Agent、查看 Trace、Human Review 和报告。前端不改变 Agent 逻辑，重点是把 P1-P5 的 API 变成可操作、可演示、可排查的闭环。
