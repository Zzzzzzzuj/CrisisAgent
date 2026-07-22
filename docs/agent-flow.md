# Agent Flow

## 总体说明

CrisisAgent 的 Agent 之间不是直接相互调用，而是由 `workflow.py` 统一编排。

每个 Agent 的通信方式都很简单：

- 输入：一个 `str` 或 `dict payload`
- 输出：一个结构化 `dict`
- workflow 负责把上一步输出拼成下一步输入

这让整条链路非常容易跟踪。

---

## Agent A：舆情分析 Agent

### 输入是什么

- `event: str`

### 输出字段是什么

```json
{
  "risk_level": "",
  "public_emotion": "",
  "keywords": [],
  "recommended_tone": "",
  "analysis_summary": ""
}
```

### 为什么需要它

因为后面的所有 Agent 都需要一个稳定的“起点判断”。

如果一开始不先把风险和情绪抽出来，后面文案 Agent 就容易：

- 语气不稳
- 风险判断漂移
- case 间风格不一致

它相当于整个链路里的“感知层”。

### 它怎么和后面通信

workflow 把它的输出放进：

- Agent C 第一版的 `sentiment_analysis`
- Agent E 的 `sentiment_analysis`

---

## Agent C：策略文案 Agent（第一版）

### 作用

把“危机事件 + 舆情判断”转成第一版对外回应。

### 输入输出

输入：

```json
{
  "event": "...",
  "sentiment_analysis": {...}
}
```

输出：

```json
{
  "statement": "...",
  "strategy": "...",
  "tone": "...",
  "notes": "..."
}
```

### 为什么单独拆出来

因为写文案和判断风险不是一回事。

单独拆出文案 Agent 后，后面做 Prompt 调优、文案风格控制、A/B 测试都更容易。

---

## Agent D：红队攻击 Agent

### 红队攻击逻辑

它不是负责“写得更好看”，而是负责“找漏洞”。

它会从公众和媒体视角去挑问题，比如：

- 回应是不是太模板化
- 有没有显得在拖延
- 有没有只说排查不说整改
- 共情是不是不够具体

### 为什么需要对抗检查

真实危机公关里，第一版声明几乎总是有被攻击的空间。

如果不做这一步，后面很容易出现：

- 法务安全但舆论失败
- 说得很稳，却激怒公众

所以红队是帮系统提前做“舆论逆向压力测试”。

### 输入输出

输入：

```json
{
  "event": "...",
  "draft": "第一版声明"
}
```

输出：

```json
{
  "issues": [],
  "attack_summary": "",
  "suggestions": []
}
```

---

## Agent B：合规审查 Agent

### 合规审查流程

它会看两类东西：

1. 第一版声明本身有没有法律风险
2. 红队反馈里哪些点需要吸收进合规修订

### 如何结合红队反馈

这一步不是简单法务审核，而是“法务 + 舆情联合审视”。

它除了给出：

- `legal_risks`
- `safe_points`
- `revision_advice`

还会补充：

- `public_opinion_suggestions`
- `integrated_revision_tasks`

这两个字段就是给第二版 Writer 用的。

### 输入输出

输入：

```json
{
  "event": "...",
  "draft": "第一版声明",
  "redteam_review": {...}
}
```

输出核心字段：

```json
{
  "legal_risks": [],
  "safe_points": [],
  "revision_advice": [],
  "public_opinion_suggestions": [],
  "integrated_revision_tasks": []
}
```

---

## Agent C：策略文案 Agent（第二版）

### 如何根据反馈修改

第二版不是重写，而是“带着反馈修订”。

它会综合：

- 第一版声明
- 红队攻击意见
- 合规审查意见

然后生成更稳的版本。

### 输入输出

输入：

```json
{
  "event": "...",
  "first_draft": {...},
  "redteam_review": {...},
  "legal_review": {...}
}
```

输出：

- 新的 `statement`
- 修订策略
- 修订摘要

### 为什么要有第二版

这是这个 workflow 里“闭环”的关键。

没有第二版，就只有“发现问题”，没有“吸收问题”。

---

## Agent E：最终决策 Agent

### 最终决策和评分

它负责最后做两件事：

1. 确定 `final_statement`
2. 给出可解释的分数

输出：

```json
{
  "final_statement": "",
  "scores": {
    "legal_safety": 0,
    "empathy": 0,
    "robustness": 0
  },
  "decision_summary": ""
}
```

### 为什么需要它

因为系统最终不只是要“给一个文本”，还要能告诉你：

- 这个版本法务安全吗
- 共情够不够
- 整体稳不稳

这对后续评测和产品化很重要。

---

## Workflow 怎么传递数据

整个通信方式很简单，都是 workflow 明确拼 payload。

文字版数据流如下：

`event`
→ Agent A
→ `sentiment_analysis`
→ Agent C 第一版
→ `first_draft`
→ Agent D
→ `redteam_review`
→ Agent B
→ `legal_review`
→ Agent C 第二版
→ `second_draft`
→ Agent E
→ `final_statement + scores`

这个设计的好处是：

- 输入输出全是显式 dict
- trace 记录天然完整
- 单 Agent 测试容易写
- 以后接数据库、消息队列或异步任务也比较顺滑
