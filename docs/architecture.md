# CrisisAgent Architecture

## 项目解决的问题

CrisisAgent 面向企业危机公关场景，目标是把“收到危机事件 -> 形成可发布声明 -> 做风险校验 -> 输出最终决策”这条链路工程化。

它解决的不是单点文案生成问题，而是一个更接近真实业务流程的问题：

- 先判断舆情风险和公众情绪
- 再生成第一版回应
- 再做对抗性检查和合规审查
- 再修订文案
- 最后给出最终声明和评分

## 为什么采用多 Agent 架构

如果只用一个大模型一步生成最终声明，会有几个问题：

- 角色混在一起，不容易控制输出质量
- 很难定位到底是哪一步出了问题
- 很难做局部替换、局部优化
- 不利于后续接入不同数据源和能力，比如法务知识库

多 Agent 的好处是把复杂任务拆成可解释的子任务：

- Agent A 负责“看懂舆情”
- Agent C 负责“写文案”
- Agent D 负责“挑刺”
- Agent B 负责“法务与合规”
- Agent E 负责“拍板和评分”

这样每一步都可以单测、替换、观察、评估。

## 整体技术栈

- Python
- FastAPI
- Pydantic
- 规则函数 + mock Agent
- OpenAI-compatible HTTP LLM Client
- pytest
- JSON / Markdown evaluation reports

## FastAPI 后端结构

当前后端入口比较克制，结构很清晰：

- `backend/main.py`
  - API 入口
  - 暴露 `/api/crisis/run`
  - 暴露 session 查询接口
- `backend/workflow.py`
  - 唯一 workflow 编排入口
  - 串联多 Agent
  - 记录 trace
- `backend/agents/`
  - 每个 Agent 一个文件
  - 每个文件内部支持 `mock / llm` 双模式
- `backend/config.py`
  - 统一读取 `AGENT_MODE` 和 LLM 配置
- `backend/llm_client.py`
  - 统一封装模型调用
- `backend/prompt_loader.py`
  - 统一读取 Prompt 模板
- `backend/utils/json_parser.py`
  - 统一解析模型 JSON 输出
- `backend/storage.py`
  - 内存级 session 保存与查询

## Workflow 编排方式

核心编排在 `backend/workflow.py`，顺序固定，不在 Agent 内部串调用，避免职责混乱。

文字流程图如下：

用户输入事件
 ↓
FastAPI
 ↓
workflow
 ↓
Agent A 舆情分析
 ↓
Agent C 策略文案（第一版）
 ↓
Agent D 红队攻击
 ↓
Agent B 合规审查
 ↓
Agent C 策略文案（第二版）
 ↓
Agent E 最终决策
 ↓
Trace + Evaluation

## Agent 调用关系

workflow 内部的输入传递关系是显式 dict 传递，不搞隐式共享状态。

- Agent A 输入：`event`
- Agent C 第一版输入：`event + sentiment_analysis`
- Agent D 输入：`event + first_draft.statement`
- Agent B 输入：`event + first_draft.statement + redteam_review`
- Agent C 第二版输入：`event + first_draft + redteam_review + legal_review`
- Agent E 输入：`event + second_draft + sentiment_analysis + redteam_review + legal_review`

这种写法的优点是：

- 数据流清楚
- 调试容易
- trace 容易记录
- 后续改 Agent 不容易破坏整体

## LLM / Mock 双模式设计

项目目前已经把主链路上的关键 Agent 做成了双模式：

- `mock`
  - 默认模式
  - 不依赖任何模型配置
  - 用规则或固定模板稳定跑通
- `llm`
  - 通过 Prompt + LLM Client + JSON Parser 工作
  - 对外接口不变

统一路径是：

输入
 ↓
load_prompt(...)
 ↓
call_llm(...)
 ↓
parse_llm_json(...)
 ↓
字段校验
 ↓
normalize 输出

## Fallback 机制

这是这个项目工程化里很关键的一点。

当 Agent 处于 `llm` 模式时，如果出现下面任一情况：

- 网络失败
- 模型超时
- JSON 解析失败
- 字段缺失
- 类型错误

就会自动 fallback 到 mock。

这样带来的价值是：

- workflow 不会因为单个 Agent 出错而整体崩掉
- API 结构保持稳定
- 测试和评测可以继续跑
- 方便逐个 Agent 渐进式接入真实模型

## Trace 可观测设计

每一步 Agent 都会记录到 `agent_trace`，现在的 trace 字段包括：

- `agent`
- `name`
- `input`
- `output`
- `start_time`
- `end_time`
- `status`
- `mode`
- `fallback`

这让我们可以回答很多工程问题：

- 哪一步慢
- 哪一步经常 fallback
- 当前运行到底走的是 mock 还是 llm
- 某个 case 是在哪一步开始偏的

## Evaluation 体系

项目现在已经有独立的 `evaluation/` 模块。

它做的事情是：

- 读取测试案例
- 调用真实 workflow
- 收集 Agent A 输出、最终 scores、trace
- 统计 accuracy、fallback、耗时
- 输出 JSON 报告和 Markdown 报告

目前 evaluation 关注的核心指标包括：

- `risk_accuracy`
- `emotion_accuracy`
- `tone_accuracy`
- `fallback_rate`
- `average_duration_ms`
- `agent_metrics`
- `category_metrics`

## 当前架构的特点

这个项目的特点不是“模型有多强”，而是“结构已经很适合继续长大”：

- API 层很薄
- workflow 入口唯一
- Agent 边界清楚
- 输出结构稳定
- fallback 机制完整
- trace 和 evaluation 都已经接上

这也是它比较适合面试讲解的地方：不是 demo，而是一个已经有明显工程边界感的 Agent 系统。
