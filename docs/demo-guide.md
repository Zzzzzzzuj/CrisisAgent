# CrisisAgent Demo Guide

本文档用于 GitHub 展示和面试演示，目标是在 5 到 8 分钟内讲清楚 CrisisAgent 的产品价值和工程架构。

## 1. Demo 案例

案例文件：

```text
demo/cases.json
```

内置案例：

- `food_safety`: 食品安全危机
- `data_leak`: 数据泄露危机
- `general_complaint`: 普通服务投诉

## 2. 命令行 Demo

运行：

```bash
python scripts/run_demo_cases.py
```

脚本会输出：

- case 名称
- dynamic runtime 结果
- plan
- agent trace
- RAG 命中
- memory 命中
- evaluation
- human gate 状态
- final statement

建议讲解方式：

1. 先展示 food_safety，说明高风险事件会触发更严格的审核逻辑。
2. 再展示 data_leak，说明系统可以覆盖数据隐私类危机。
3. 最后展示 general_complaint，说明系统也能处理低风险普通投诉。

## 3. Dashboard Demo

启动后端：

```bash
uvicorn backend.main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:5173
```

推荐演示路径：

1. 首页“危机案例管理中心”
   - 说明系统以 Crisis Case 为核心，而不是 session。
   - 展示案例列表和审核状态。

2. 新建危机案例
   - 输入食品安全事件。
   - 点击生成响应方案。

3. 进入案例详情
   - 展示风险等级。
   - 展示舆情分析。
   - 展示 AI 生成声明。
   - 展示 Human Review。

4. 展开高级分析
   - 展示 Agent Trace。
   - 展示 RAG 和 Memory 信息。
   - 展示 runtime metrics。

## 4. 面试讲解脚本

可以这样开场：

> CrisisAgent 是一个企业危机响应 Agent Platform。它不是让一个大模型直接生成公关稿，而是把真实危机响应拆成 Planner、Executor、多个专业 Agent、RAG、Memory、Evaluation 和 Human Review。前端面向业务用户展示 Crisis Case，底层保留 Agent Trace 和 Metrics，方便调试和复盘。

重点讲 4 个点：

- 为什么多 Agent：职责拆分，方便定位和替换。
- 为什么需要 RAG：合规审查不能靠模型编法律依据。
- 为什么需要 Human Gate：危机公关是高风险场景，不能全自动发布。
- 为什么需要 Evaluation：Agent 系统不能只看单次输出，要持续评测。

## 5. 常见问题

### 为什么不用一个 LLM？

一个 LLM 可以做 demo，但工程上不可控。拆成多 Agent 后，每一步都有输入输出、trace、fallback 和测试。

### RAG 放在哪里？

当前主要放在 Legal Agent，因为合规审查最依赖稳定知识库。

### Memory 和 RAG 有什么区别？

RAG 是法规、规范、知识库；Memory 是企业历史危机经验。

### Human Review 如何恢复？

Runtime 会把 AgentState 保存到 checkpoint。人工 approve 后，系统可以从 checkpoint 恢复执行。

### 这个项目如何继续生产化？

可以接数据库、权限系统、消息队列、真实向量数据库、线上监控，以及更严格的人工标注评测集。
