# P22.1 Trace Failure Diagnosis 与 Harness 离线对比

## 定位

本阶段把已有 Trace、Evidence Quality、ToolResult、ContextPack 和 Review 状态映射为确定性 failure tags。Analyzer 只负责解释发生了什么和建议检查哪个 Harness 区域，不会修改 HarnessSpec。

支持的标签包括 retrieval、evidence、tool、context 和 review 五类问题。没有异常的运行返回空标签，避免把正常结果误报成失败。

## 离线对比

`compare_harnesses()` 当前复用 Eval Center 的本地 Golden Cases，在同一批 Case 上分别生成 baseline 与 candidate 结果，记录 `harness_id`、`version`、`spec_hash`、Case 结果、失败标签和人工审核状态，并输出完成率、证据质量、工具失败率、人工审核率及差异。完整 Replay Runner 尚未实现，Replay Case 目前只能作为诊断来源和后续验证标识保存。

Candidate 必须来自 P21 已人工创建或复制的 HarnessSpec。P22.1 不自动生成、启用或发布候选版本，也不调用真实 Agent、LLM、网络或外部数据库。

## API

- `POST /api/harness-comparisons`：创建离线对比任务。
- `GET /api/harness-comparisons`：查询历史任务。
- `GET /api/harness-comparisons/{comparison_id}`：查询完整报告。

结果保存于 `data/harness_comparisons.runtime.json`，可通过 `HARNESS_COMPARISON_STORE_PATH` 指向测试临时文件。

## 面试讲解版

“遇到 Bad Case，我先用规则从 Trace 定位是检索、证据、工具、上下文还是审核范围问题，再用同一批离线 Golden Cases 对比 baseline 和 candidate Harness。系统只生成诊断和对比报告，不自动修改或启用配置；候选版本是否生效仍由人工审核和评测门槛决定。”
