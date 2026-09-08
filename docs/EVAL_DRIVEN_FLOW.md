# Eval-driven CrisisAgent Flow

## 项目定位

CrisisAgent 是一个 Eval-driven 企业舆情危机响应工作台：它不仅执行多 Agent 危机响应，也记录各层证据、状态和离线评估结果，用于持续发现回归与失败模式。

```text
Eval Dataset
  -> Source Registry
  -> Ingestion Run
  -> normalize / deduplicate / cluster
  -> CrisisEvent
  -> Crisis Urgency Score
  -> Crisis Radar
  -> Agent Run
  -> Sentiment / Writer / RedTeam / Legal RAG / WriterV2 / Decision
  -> Output Eval / RAG Eval / Tool Eval / Safety Eval
  -> Human Review
  -> Trace / Review / Report
  -> Eval Center / Golden Cases / CI Regression Gate
```

## 各层评估

- Data Eval：采集结果、来源状态和 `no_match`/失败语义；
- Event Cluster Eval：事件来源、指纹、风险与事实状态；
- Urgency Eval：SEV 规则和人工审核优先级；
- RAG Eval：retrieval hit、污染率、evidence quality 与 ablation；
- Agent Output Eval：Runtime evaluation、结构化 trace 和声明草稿安全边界；
- Tool Eval：schema、timeout、retry、fallback、budget 与 loop detection；
- Safety Eval：Guardrail、Human Review trigger、审批作用域；
- Report Faithfulness Eval：报告仅使用已有 run，且不表示自动发布。

## 已完成的评估能力

- RAG retrieval eval 与 baseline/regression；
- Evidence Quality Gate；
- Runtime evaluation；
- Tool Reliability Evaluation；
- Human Review triggers 与审批作用域回归；
- Report safety boundary；
- Crisis Radar urgency rules；
- Eval Center 的 ingestion、event、urgency、agent run、report、tool 汇总与 regression 对比。
- Golden Case 数据契约校验与命令行 Eval CI Gate。

## 不做什么

- 不为了展示而堆叠新 Agent；
- 不做无限论坛采集或全网乱爬；
- 不把“接上 RAG”当作检索效果证明；
- 不把 MCP 暴露成工具就当作系统效果证明；
- 不把离线规则评估伪装成真实企业线上指标。

## 面试讲解

### 30 秒版

> CrisisAgent 的核心不是只跑一个多 Agent 链路，而是把评估贯穿到数据、检索、工具、运行时和报告层。Eval Center 会保存离线 EvalRun，并对比最近两次的通过率和新增失败项，让每次改 ingestion、紧急度规则或工具执行器后都能发现回归。

### 1 分钟版

> 我把系统拆成“执行链路”和“评估链路”。执行链路从白名单采集到 CrisisEvent、Agent Run、Human Review 和报告；评估链路分别检查采集状态、事件字段、Crisis Radar 紧急度、RAG evidence、工具可靠性、审核触发和报告安全边界。P9 的 Eval Center 不重跑 Agent，而是读取已有记录和确定性规则，生成可保存的 EvalRun；连续运行后还能发现新增失败和恢复用例。这比只展示某次成功生成更接近工程迭代方式。

### STAR 版

**Situation：** 系统已有 Agent、RAG、工具治理和工作台，但各类验证分散在测试和脚本中，业务人员无法看到一次版本变更是否影响完整闭环。  
**Task：** 不改变 Agent 主流程的前提下，把已有离线验证变成可查询、可比较的产品能力。  
**Action：** 新增 EvalRun JSON store、六类规则评估、overview 与 regression API，并在 Workbench 展示通过率、维度汇总和失败项。工具维度复用已有 fake-tool reliability suite，避免真实网络和模型依赖。  
**Result：** 系统能从“展示能力”升级为“记录并比较质量信号”；后续可在此基础上接 golden cases、人工抽检和 CI gate。
