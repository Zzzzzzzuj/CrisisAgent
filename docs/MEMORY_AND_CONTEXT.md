# Case Memory And ContextPack

## 定位

P20 增加的是企业危机响应的长期案例记忆，不是用户闲聊偏好记忆。它保存经过完成或人工审核的事件摘要，用于帮助后续相似事件检索和人工复盘。

## 四层信息

- 短期记忆：AgentState 中的当前事件、Agent 结果和 trace。
- 任务记忆：Checkpoint 保存一次运行的状态，支持恢复。
- 长期知识：Legal RAG 中的法规和法律知识。
- 长期案例记忆：Case Memory 中的历史响应策略、法律风险、RedTeam 和 Human Review 摘要。

未核实、来源冲突或尚未审核的外部线索不能自动进入案例记忆。memory 不保存完整新闻全文、API key、system prompt 或完整 tool arguments。

## Memory Retriever

第一版使用确定性评分，不引入向量库或 LLM。评分参考主体、危机类型、风险等级、事实状态、tags、风险关键词和轻量时间近因，并返回 score 与 matched_reasons。

## ContextPack

ContextPack 在进入后续模型调用前提供结构化、可审计的上下文预览：

~~~text
CrisisEvent / event text
-> Public Signals / Alerts / Legal Evidence / Case Memory
-> deterministic filtering and clipping
-> ContextPack
~~~

默认上限为 5 条 Public Signal、3 条 Alert、3 条 Legal Evidence 和 3 条相关案例记忆；文本预览最多 500 字，丢弃的类别写入 dropped_fields。它不改变现有 Agent 顺序和 Prompt 主体，当前也不强制注入 AgentState。

## API

- GET/POST/PATCH /api/case-memories
- GET /api/case-memories/{memory_id}
- POST /api/case-memories/{memory_id}/archive
- POST /api/context-pack/build

## Crisis Lifecycle Memory

企业危机通常不是一次性问答：首轮声明后，舆论可能继续发酵、转向，或出现相似事件。Case Memory 因此支持可选的 `case_group_id`、`round_index` 和 `previous_memory_id`，并保存经过审核的上一轮声明摘要、公众反应、未解决的 RedTeam 问题、法律约束和避免重复的要点。它只保存摘要，不保存完整新闻、system prompt、API key 或完整工具参数；未核实、冲突或不确定的信号不能自动进入长期记忆正文。

Memory Retriever 仍是离线确定性规则：同一危机组、相近轮次、恶化结果，以及未解决的 RedTeam/法律约束重叠会提高相关性分数。返回 `matched_reasons`，便于解释为什么选中某一轮历史案例。

ContextPack 请求可传 `target_agent`：`sentiment`、`writer`、`redteam`、`legal`、`writer_v2` 或 `decision`。构建器在原有数量和 500 字预览上限基础上，生成 `agent_specific_focus`：RedTeam 看到已处理和未解决攻击面，Legal 看到历史法律约束和事实状态，Writer 看到上一轮声明及变化，Decision 看到结果趋势和是否需要二次回应。当前仍是独立 Preview，不强行改写主 Agent Prompt 或顺序。

写操作需要 admin/operator，legal_reviewer 和 viewer 只读；写操作会写入 Audit Log。ContextPack 构建允许 admin/operator/legal_reviewer。

## 验证和边界

backend/api/memory_eval.py 提供离线指标：memory relevance、context budget compliance、critical fact coverage、unsafe memory inclusion count 和 dropped noise count。当前使用 JSON storage 和本地单元测试，不访问网络、LLM、Redis、PostgreSQL、BGE 或 Milvus。

## 面试讲法

> 我的长期记忆不是保存用户聊天历史，而是保存已经完成或经过人工审核的企业危机案例摘要。当前事件由 AgentState 和 Checkpoint 管理，法律知识由 RAG 管理，历史响应经验由 Case Memory 管理。新事件到来后，我用确定性规则检索相似案例，再通过 ContextPack 只保留有限数量的信号、告警、法律证据和案例摘要，避免把所有历史内容一次性塞进 Prompt。未核实信息不能自动进入长期记忆，避免 memory pollution。
