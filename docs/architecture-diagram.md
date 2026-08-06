# CrisisAgent Architecture Diagram

本文档用图示方式说明 CrisisAgent 的产品结构、Dynamic Runtime、Agent 协作和可观测链路，方便 GitHub 展示和面试讲解。

## 1. 产品视角

```mermaid
flowchart TD
    A["企业危机事件"] --> B["Crisis Case 管理中心"]
    B --> C["AI 风险研判"]
    C --> D["AI 生成声明"]
    D --> E["Human Review 企业审核"]
    E --> F{"审核结果"}
    F -->|通过| G["可发布声明"]
    F -->|驳回| H["重新修订或终止"]
    B --> I["高级分析"]
    I --> J["Agent Trace"]
    I --> K["RAG 命中"]
    I --> L["Memory 引用"]
    I --> M["Runtime Metrics"]
```

## 2. Dynamic Runtime 架构

```mermaid
flowchart TD
    A["User Event"] --> B["Planner"]
    B --> C["Plan Validator"]
    C --> D["AgentState"]
    D --> E["Executor"]
    E --> F["Agent Adapter"]
    F --> G["Sentiment Agent"]
    F --> H["Writer Agent"]
    F --> I["Redteam Agent"]
    F --> J["Legal Agent"]
    F --> K["Decision Agent"]
    G --> D
    H --> D
    I --> D
    J --> D
    K --> D
    D --> L["Runtime Evaluator"]
    L --> M["Policy"]
    M --> N["Human Gate"]
    N --> O["Checkpoint"]
    O --> P["Resume"]
```

## 3. Agent 协作链路

```mermaid
flowchart LR
    A["事件输入"] --> B["Agent A 舆情分析"]
    B --> C["Agent C 文案生成"]
    C --> D["Agent D 红队攻击"]
    D --> E["Agent B 合规审查"]
    E --> F["Agent C 二次修订"]
    F --> G["Agent E 最终决策"]
    G --> H["final_statement + scores"]
```

## 4. RAG / Memory / Tools 位置

```mermaid
flowchart TD
    A["Agent 输入"] --> B["Context Manager"]
    B --> C["Prompt"]
    D["RAG Knowledge Base"] --> E["Hybrid Retriever"]
    E --> F["Reranker"]
    F --> C
    G["Memory Store"] --> H["Memory Retriever"]
    H --> C
    I["Tool Registry"] --> J["Tool Calling"]
    J --> C
    C --> K["LLM or Mock Agent"]
```

## 5. Human Gate 与 Resume

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> RUNNING
    RUNNING --> WAITING_HUMAN: high risk or low quality
    WAITING_HUMAN --> RUNNING: approve
    WAITING_HUMAN --> FAILED: reject
    RUNNING --> COMPLETED: evaluation passed
    RUNNING --> FAILED: max iterations reached
```

## 6. Observability

```mermaid
flowchart TD
    A["Agent Execution"] --> B["Trace"]
    B --> C["start_time / end_time"]
    B --> D["status / fallback"]
    B --> E["rag / memory / tools"]
    B --> F["duration_ms"]
    F --> G["Metrics API"]
    G --> H["Dashboard Advanced Analysis"]
```

## 面试讲解重点

- 系统不是单 LLM，而是一个可编排 Agent Runtime。
- Agent 之间不直接互相调用，而是通过 AgentState 共享结果。
- RAG 放在 Legal Agent，Memory 放在 Writer Agent，职责边界清晰。
- Human Gate 保证高风险场景不会完全自动化发布。
- Checkpoint Resume 让审核中断后的 runtime 可以恢复。
- Dashboard 面向业务用户，高级分析面向开发和调试。
