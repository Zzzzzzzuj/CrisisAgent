# P28 ContextPack Runtime Integration

## 目标

P28 将原本独立的 ContextPack Preview 接入固定 Workflow 和 Dynamic Runtime。它不改变六步顺序，也不把所有历史内容无差别放进每个 Agent，而是在目标 Agent 执行前生成一个有预算、可审计的角色专属 Pack。

## 真实接入范围

`Executor` 和固定 Workflow 的统一 step 入口会调用 `ContextPackRuntimeProvider`。当前接入的目标角色是 `writer`、`redteam`、`legal`、`writer_v2` 和 `decision`；`sentiment` 不强制注入。Provider 读取本次运行固定的 Harness snapshot、ingestion metadata、已有结果和 Case Memory，并调用既有的确定性 `build_context_pack`。

不同角色保留不同重点：Writer 关注事实和历史回应，RedTeam 关注风险信号与未解决攻击面，Legal 关注证据和事实状态，Writer V2 关注审核意见与修订约束，Decision 关注风险变化和人工确认项。

## 状态、Trace 与恢复

完整 Pack 快照保存在 `AgentState.metadata["context_pack_snapshots"]`，因此会随 Checkpoint 序列化；同一 Agent 已有快照时优先复用，不会因后续 Case Memory 变化而重建历史上下文。Trace 只记录目标角色、`context_pack_hash`、选中数量、裁剪数量、水位线和降级标记，避免响应中重复暴露大段上下文。

LLM Agent 会收到 `context_pack_text`；Mock Agent 也会构建和记录 Pack，但仍使用原有确定性输出，保证离线回归稳定。Writer 在存在运行时 Pack 时复用 Pack，不再额外检索一次旧 Memory Context。

## 降级边界

没有 Memory、没有 Evidence 或 Pack 构建异常时，Provider 生成最小安全 Pack 并标记 `degraded`，主流程继续执行。预算裁剪由既有风险水位线完成，并保留关键事实字段、`dropped_fields` 和 `safety_notes`。本阶段没有接入真实模型、网络、Redis、PostgreSQL 或 BGE，也不代表线上 Token 成本和真实模型效果。

## 面试讲解版

之前 ContextPack 只能通过 Preview API 验证，主流程不会自动使用。P28 把它放到 Executor 的统一入口，在每个关键 Agent 前按角色生成一次并缓存快照：这样 Writer、RedTeam、Legal 看到的不是同一份历史上下文，恢复时也不会因为记忆库变化而漂移。为了降低改造风险，Mock 路径只记录 Pack、不改变旧输出；如果构建失败则降级为最小安全上下文，而不是让一次记忆检索故障拖垮整条危机响应链路。
