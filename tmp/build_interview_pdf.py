from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "CrisisAgent_趣丸AI_Native面试速背稿.pdf"


def register_font() -> str:
    candidates = [
        ("MicrosoftYaHei", Path("C:/Windows/Fonts/msyh.ttc")),
        ("SimSun", Path("C:/Windows/Fonts/simsun.ttc")),
        ("DengXian", Path("C:/Windows/Fonts/Deng.ttf")),
    ]
    for name, path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    raise FileNotFoundError("No Chinese font found under C:/Windows/Fonts")


FONT = register_font()


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(text).replace("\n", "<br/>"), style)


def entry(q: str, a: str, follow: str = "") -> tuple[str, str, str]:
    return q, a, follow


SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "一、Agent 与工作流",
        [
            entry("1. 为什么 Multi-Agent，而不是一个模型加一个大 Prompt？", "我把风险分析、写稿、RedTeam、Legal 和 Decision 拆成职责明确的角色。这样每一步都有清晰输入输出，问题能定位，某个环节可以单独优化，也能在高风险节点加入人工审核。不是把复杂任务交给一个模型自由发挥。", "不要说每个 Agent 都是独立大模型；核心价值是职责、状态和审核边界。"),
            entry("2. 为什么固定 6 步 Workflow，不让 LLM 动态规划？", "舆情危机有明确依赖：先分析风险，再写初稿，再由 RedTeam 和 Legal 审查，之后二次改稿，最后决策。固定的是安全骨架，节点内部仍然会做检索、证据判断、工具重试和审核决策。这样更容易复现、审计和评测。", "五类业务角色、六个步骤，因为 Writer 执行两次。"),
            entry("3. Agent 之间怎么通信？AgentState 怎么传？", "每个 Agent 输出结构化结果，Executor 写入共享运行状态；下一个 Agent 只读取自己需要的字段。例如 RedTeam 的问题和建议会进入 Legal 的输入，Legal 再结合证据生成审核结果。Trace 记录过程，Checkpoint 保存状态用于恢复。", "不是把完整 Trace 原样拼给下一个 Agent。"),
            entry("4. Skill 是什么？和 Agent、Tool 有什么区别？", "Agent 是完整业务角色，Skill 是可复用的专业能力，Tool 是底层可执行函数或接口。例如 Legal Agent 可以使用证据核验 Skill，底层通过 ToolRunner 执行并校验。", "Skill 当前采用规则化、白名单方式，不等于任意工具调用。"),
            entry("5. Skill 是谁选择的？为什么不让 LLM 自由选？", "当前由规则化 Skill Selector 根据 Agent 角色、状态和白名单选择。RedTeam 可做风险研判，Legal 可做证据核验和上下文获取，Writer V2 可做声明约束检查。程序负责权限、预算和执行，LLM 不可绕过这些边界。", "未来也只能让模型提出候选，再由程序审核。"),
            entry("6. 重试和降级有什么区别？", "重试是同一能力再次执行，适合临时超时；降级是原路径不可靠时切换到备用路径。例如工具第一次超时可重试，仍失败则返回结构化错误；真实 LLM 失败时可降级到 mock，RAG 管线失败时可使用关键词检索并标记 fallback。", "降级不能伪装成正常成功，必须记录实际路径。"),
            entry("7. 什么叫最小安全结果？", "当完整能力不可用时，系统不编造结论，而是返回足以继续控制流程的信息。例如法律检索失败时，不生成确定的法律依据，只保留事件和失败状态，标记证据低置信度并进入人工审核。", "最小安全结果的核心是可控、可解释，不是尽量生成更多内容。"),
            entry("8. 哪些情况必须进入 Human Review？", "事实未确认、来源冲突、证据低置信、检索失败或污染过高、关键工具失败、审核范围不匹配，以及最终决策认为声明不能直接交付时，都应由审核策略判断转人工。系统不会自动发布声明。", "不要简单说“所有高风险都转人工”；要说由审核策略和具体触发条件决定。"),
        ],
    ),
    (
        "二、Legal RAG 与证据",
        [
            entry("9. Evidence Quality Gate 是什么？为什么 Reranker 后还需要它？", "Reranker 只负责把候选证据重新排序，Evidence Quality Gate 负责判断结果是否足够可靠。它会检查证据是否为空、分数是否过低、来源是否匹配、污染率是否过高和是否发生 fallback；不合格就标记低置信度并可转人工。"),
            entry("10. Retrieval Gate 和 Evidence Quality Gate 的区别？", "Retrieval Gate 在检索前判断要不要查；Evidence Quality Gate 在检索后判断查到的结果能不能信。前者解决无效检索，后者解决证据质量。"),
            entry("11. 检索执行了但没有可靠证据怎么办？", "系统不把空结果当成没有法律风险。Legal 保留空证据和失败元数据，Evidence Quality Gate 标记 no_evidence 或低置信度，Human Review Policy 再决定转人工。主流程可以继续，但不会把这次结果当成充分法律依据。"),
            entry("12. 两条法律证据互相冲突怎么办？", "保留来源和冲突状态，不强行选一条当真相。证据质量被标记为冲突或低置信度，Legal 可以说明冲突，最终进入人工法务审核。声明中不能把冲突信息写成确定事实。"),
            entry("13. 为什么关键词加 BGE？", "关键词检索擅长法规名称、固定术语和条款表达；向量检索擅长用户改写和语义相近表达。两者结合可以兼顾精确命中和语义召回。当前源码支持 BGE 配置，但默认离线模型可为 hash，不能把所有默认运行都说成 BGE。"),
            entry("14. 两路结果怎么融合？", "每路先取候选，按 chunk_id 去重；没有编号时按 source 加 text 去重。当前是加权分数融合，不是 RRF：默认 hybrid_score 等于 0.5 乘关键词分数加 0.5 乘向量分数，未命中的一路按 0 处理。多个改写查询的结果还会再次去重，并保留同一切片的较高混合分数。"),
            entry("15. Retriever 和 Reranker 的区别？为什么不直接重排全库？", "Retriever 负责从全库快速召回一个候选池，Reranker 负责在候选池内精排。全库重排计算更重、噪声更多，而且无法体现先召回再精排的分层结构。项目当前 Reranker 是规则型，不是 Cross-Encoder 或 LLM。"),
            entry("16. Recall@3 都是 90%，为什么还能说 Reranker 有效果？", "因为 Reranker 的目标不只是提高召回，还要降低错误领域资料进入上下文。项目中 Recall@3 保持 0.90，但来源类别匹配率提升、污染率下降，说明正确资料没有少召回，同时结果更干净。"),
            entry("17. 47.22% 到 32.22% 的污染率是什么？", "每个案例先把来源分为可接受、中性和禁止三类，污染率等于禁止来源数除以可评估来源总数，再对案例求平均。它衡量的是跨领域资料混入，不是模型幻觉率。下降后 Legal 更少受到错误领域法规干扰。"),
        ],
    ),
    (
        "三、状态、恢复与评测",
        [
            entry("18. Checkpoint 是什么？任务中途挂了怎么恢复？", "Checkpoint 是某个步骤完成后的状态快照，包含当前事件、已有 Agent 结果、Trace、Harness 和上下文快照。恢复时读取最近快照，从未完成步骤继续，不重复已经完成的步骤。"),
            entry("19. Checkpoint 和 Memory 的区别？", "Checkpoint 服务于当前任务恢复，保存这一次运行到哪里、当时用什么配置和上下文；Memory 服务于未来任务复用历史案例，例如上一轮声明、法律限制和未解决的红队问题。一个是短期运行状态，一个是跨任务长期经验。"),
            entry("20. Trace 记录什么，怎么定位？", "Trace 记录 Agent 名称、开始结束时间、状态、输出摘要、错误、模型或 RAG 元数据、Harness 版本、ContextPack 引用和 Skill 结果。排查时先看哪一步失败，再看输入来源、证据质量、工具错误码和是否发生 fallback。"),
            entry("21. 怎么评价 Agent 系统好不好？", "我分层评估：单元和集成测试看工程行为，固定案例看风险和证据质量，RAG 指标看召回和污染，工具评测看超时重试降级，人工审核测试看高风险是否被拦截。没有唯一标准答案时，重点评估事实、证据、约束和安全，而不是只看文本像不像。"),
            entry("22. 750 passed 和 Eval Center 74/74 测什么？", "750 passed 说明自动化测试中的代码、接口、权限、状态、RAG、工具和恢复行为没有回归；74/74 是离线评测案例全部通过预设门槛，检查任务完成、证据质量、失败标签、工具稳定性和人工审核。两者不是模型得分，也不是生产验证。"),
            entry("23. 750 个测试全过能证明 Agent 效果好吗？", "不能。它证明工程行为稳定，不证明真实企业数据、真实模型长期效果或生产 QPS。还需要脱敏真实案例、法务和公关人员评审、线上成本延迟监控和持续回归。"),
            entry("24. 为什么固定评测集要冻结？", "如果每次发现失败就把案例删掉或改成更容易通过，指标会失真。冻结集用于稳定比较 baseline 和 candidate；新增案例进入开发集或新的版本，不能修改原有成绩口径。"),
            entry("25. 换模型怎么判断比 DeepSeek 好？", "固定 Prompt、输入和 Case，只替换模型，比较任务完成率、结构化输出成功率、法律风险、证据引用、工具调用、延迟、成本和失败降级。不能只看通用榜单，也不能只看一两个漂亮样例。"),
            entry("26. CrisisAgent 最大不足是什么？", "目前仍是具备生产化思路的工程原型，不是已经上线的企业 SaaS。真实数据规模、权限体系、数据库和多租户、线上模型成本、真实业务评审和运维监控都还需要继续完善。"),
            entry("27. 再给两周优先优化什么？", "第一优先是用一批脱敏真实案例补充 RAG 和危机响应评测，验证固定指标不只对 fixture 有效；第二优先是补生产化基础，包括 PostgreSQL 数据持久化、权限细化、模型调用监控和成本限额。"),
            entry("28. 距离生产还有什么差距？", "还需要可靠的数据源授权和治理、正式数据库和备份、企业级认证、多租户权限、不可篡改审计、模型供应商容灾、真实数据评测、监控告警和人工运营流程。当前不应包装成生产级系统。"),
        ],
    ),
    (
        "四、Redis、RQ、Docker 与后端",
        [
            entry("29. 为什么用 Redis-RQ？", "采集和事件分析可能较慢，不适合让 HTTP 请求一直阻塞。API 接收任务后把任务放入队列，Worker 异步处理，前端通过任务状态查询结果。Redis 负责队列存储，RQ 负责任务封装和 Worker 执行。"),
            entry("30. Redis 和 RQ 分别负责什么？", "Redis 是底层内存数据服务，在项目里保存队列和任务状态；RQ 是基于 Redis 的 Python 任务队列框架，负责入队、取任务和执行 Worker。两者不是同一个层次。"),
            entry("31. 为什么不让 FastAPI 同步执行长任务？", "同步执行会占用请求处理资源，超时后客户端也难以确认任务状态；多个任务并发时还会互相影响。队列可以把请求接收和耗时执行解耦，并支持重试、超时、死信和停滞恢复。"),
            entry("32. Worker 失败怎么办？", "记录失败状态和错误原因，根据重试策略重新入队；超过次数后进入死信或失败状态。心跳和停滞检测可以发现 Worker 长时间没有进展，必要时恢复任务。Windows 本地 smoke 使用 SimpleWorker，Linux 或 Docker 默认使用 RQ Worker。"),
            entry("33. 重复入队怎么考虑幂等？", "为任务生成 request_id 或业务唯一键，入队前检查是否已有运行记录；消费时也要检查当前状态，已完成或已处理的任务不重复执行。事件从采集 cluster 创建时也使用 run_id 加 cluster_id 做幂等。"),
            entry("34. Docker Compose 起哪些服务？", "Docker 主要用于复现本地运行环境。默认演示重点是 backend 和 frontend；PostgreSQL、Redis 等属于可选 profile，不应被默认隐式启动。它不是已经完成生产部署的证明。"),
            entry("35. Image 和 Container 的区别？", "Image 是打包好的只读运行模板，包含代码和依赖；Container 是 Image 启动后的运行实例，可以有自己的进程、网络和文件层。一个 Image 可以启动多个 Container。"),
            entry("36. FastAPI 负责什么？", "FastAPI 提供 REST API 和请求校验，连接前端与内部 Workflow、Ingestion、Event、Run、Trace、Report 和 Tool API。路由层负责接收和返回，业务逻辑仍由现有模块处理。"),
            entry("37. Pydantic 有什么作用？", "Pydantic 用于请求和响应数据校验，把类型、必填字段、枚举和范围约束放到接口边界，减少非法数据进入业务层，也让 API 文档更清晰。"),
            entry("38. 同步接口和异步接口有什么区别？", "同步接口在请求期间等待结果，适合短任务；异步任务接口快速返回任务编号，后台 Worker 执行，适合采集、长时间分析和重试。异步不等于所有函数都写成 async，而是把长任务从请求生命周期中解耦。"),
            entry("39. 大模型 API 超时怎么办？", "先设置明确 timeout，必要时对临时失败做有限重试；仍失败则走 mock 或备用路径，并记录 fallback。涉及证据和法律判断时，不能把超时当成审核通过，应该保留失败状态并考虑人工审核。"),
            entry("40. 大模型 API 怎么限流？", "我会使用令牌桶控制平均请求速率，再结合并发信号量和 Token 预算。多实例部署时把限流状态放到共享 Redis，按用户、租户和任务优先级区分配额。当前项目主要实现了受控采集限速，不能夸大为完整线上分布式限流。"),
            entry("41. Prompt 返回非法 JSON 怎么办？", "先尝试提取代码块或 JSON 对象，并修复常见尾逗号等问题；之后校验必填字段和类型。仍失败就捕获异常，记录 LLM fallback，切换到 mock 或安全降级，不把坏结果传给下一个 Agent。"),
            entry("42. DeepSeek 429 怎么办？", "把 429 视为可重试的供应商限流错误，遵守 Retry-After 时优先使用它，否则采用有上限的指数退避；重试耗尽后进入 fallback、队列延迟或人工审核，并记录错误和成本。不能无限重试。"),
            entry("43. timeout、retry、fallback 分别解决什么？", "timeout 防止单次调用无限等待；retry 处理暂时性失败；fallback 处理原路径已经不可靠或不可用的情况。三者顺序通常是先超时判定，再有限重试，仍失败后走备用能力或结构化失败。"),
        ],
    ),
    (
        "五、舆情采集与事件归并",
        [
            entry("44. Watchlist 是什么？", "Watchlist 是企业维护的监测清单，包含公司或品牌关键词、风险关键词和允许采集的来源。它限制监测范围，不等于全网无边界爬虫。"),
            entry("45. RSS、GDELT、NewsAPI 有什么区别？", "RSS 通常是来源主动提供的结构化订阅，适合低频白名单采集；GDELT 更偏全球新闻事件和元数据聚合；NewsAPI 是受接口权限和额度约束的新闻聚合服务。接入时都要统一来源、标题、链接、摘要、发布时间和来源标识。具体是否开启某个连接器，要以当前配置和授权为准。"),
            entry("46. 三个来源结构不同怎么统一？", "先定义统一的舆情条目结构，把标题、正文或摘要、链接、发布时间、来源、公司关键词和风险关键词映射进去。缺失字段使用空值或明确状态，不用猜测补全，再进入去重、聚类和风险分析。"),
            entry("47. 两篇新闻怎么判断重复？", "先做规范化：统一 URL、大小写、空白、标点和发布时间格式；再按 canonical URL、标题相似度、正文指纹和来源信息组合判断。不能只按标题，因为不同标题可能描述同一事件，也不能只按 URL。"),
            entry("48. 标题不同但同一事件怎么聚类？", "综合公司或品牌、风险类型、时间窗口、关键词、实体和内容相似度，把多条来源聚成事件簇。聚类后保留每条来源，而不是把来源正文覆盖掉。"),
            entry("49. 事件聚类依据什么？", "主要依据公司或实体、风险类别、关键对象、核心风险词、时间接近程度和文本相似性。第一阶段采用可解释的确定性规则，不把聚类结果说成复杂训练模型。"),
            entry("50. 不同来源说法冲突怎么办？", "不强行合并成一个确定事实，而是保留来源列表和冲突信息，把事实状态标记为 conflicting 或 unverified，传给后续 Legal 和 Decision，必要时进入人工审核。"),
            entry("51. 怎么区分事实已确认和未核实？", "来源报道、用户投诉和企业内部结论要分开记录。只有经过可信来源或人工确认的内容才能进入已确认事实；仅有报道或投诉时标记未核实，来源互相矛盾时标记冲突。系统不自行把报道变成事实。"),
            entry("52. 来源冲突怎么传到 Legal 和 Decision？", "冲突状态和来源条目进入事件元数据、AgentState 和 ContextPack；Legal 看到冲突后降低证据置信度并提出限制性表达，Decision 看到审核触发原因，最终判断是否需要人工确认。"),
            entry("53. 为什么真实采集要白名单、timeout 和频率限制？", "白名单限制数据范围，timeout 防止单个来源阻塞，频率限制避免对外部站点造成压力，也降低合规和封禁风险。还要遵守 robots，不登录、不绕验证码、不抓个人隐私，默认不联网。"),
        ],
    ),
    (
        "六、AI Native 与模型应用",
        [
            entry("54. 怎么判断是 Prompt 问题还是模型能力边界？", "先固定模型和输入做多次复现，检查结构化格式、上下文、指令冲突和案例覆盖；再换一个模型或简化任务对照。如果换模型仍失败，可能是任务定义或上下文问题；只有在输入和 Prompt 已稳定、不同模型表现明显差异时，才更像模型能力边界。"),
            entry("55. 新模型怎么做 A/B 测试？", "固定同一批事件、Prompt、检索结果和工具环境，只替换模型。比较结构化输出成功率、风险判断、证据引用、审核触发、任务完成率、延迟、Token 成本和失败率，保留失败样例，不只比较平均分。"),
            entry("56. temperature 怎么设置？", "高风险结构化任务更重视稳定，我会使用较低温度；创意表达可以适当放宽。但不是所有 Agent 必须相同，情感分析、Legal、Decision 更偏稳定，Writer 可以在安全约束内适度增加表达多样性，最终以固定 Case 验证。"),
            entry("57. system prompt 和 user prompt 放什么？", "system prompt 放稳定的角色、职责、边界和输出约束；user prompt 放本次事件、AgentState 中的任务数据、证据和角色化 ContextPack。不要把 API Key、内部系统提示或无关完整日志放进用户上下文。"),
            entry("58. 怎么降低大模型幻觉？", "不只依赖 Prompt。通过 Retrieval Gate、混合检索、Reranker、Evidence Quality Gate、结构化输出校验、RedTeam、Legal 审核、Human Review 和不自动发布共同降低风险。证据不足时明确标记不确定，而不是补全事实。"),
            entry("59. Structured Output 为什么重要？", "下游 Agent、审核策略和报告都需要稳定字段。如果只有自由文本，难以校验、恢复和统计。结构化输出让系统可以检查缺字段、类型错误和非法枚举，并在失败时降级。"),
            entry("60. Tool Calling 完整流程是什么？", "模型提出工具名和参数，程序检查工具白名单、权限和输入 Schema，ToolRunner 执行并处理超时、重试、输出校验和预算，再把结构化结果返回给模型。模型不能越过安全白名单直接执行发布或删除类操作。"),
            entry("61. Agent 和普通 LLM 应用区别？", "普通 LLM 应用通常是一次输入一次生成；Agent 系统包含任务状态、多个角色或步骤、工具和检索调用、执行反馈、失败恢复、审核和可追踪运行。CrisisAgent 的 Agent 不是自由发挥，而是在固定工作流和程序边界内完成判断。"),
            entry("62. Workflow 和 Agent 有什么区别？", "Workflow 规定任务按什么顺序执行，保证依赖和安全；Agent 负责某一步如何理解输入、判断风险或生成内容。CrisisAgent 是受控的 Agent Workflow。"),
            entry("63. RAG 和直接把资料放 Prompt 有什么区别？", "RAG 先根据当前问题选择相关资料，再放入上下文；直接塞全部资料会增加长度、成本和污染。CrisisAgent 还在检索前做门控，检索后做重排和证据质量检查。"),
            entry("64. AI Coding 占多少？Codex 做什么，你做什么？", "我使用 Codex 辅助扫描代码、生成测试骨架、整理文档和发现边界，但我自己负责需求拆分、接口和状态设计、风险边界、评测口径、代码审查和验证。不能把 AI 生成代码直接等同于个人理解。"),
            entry("65. AI 生成代码怎么 Review？", "先看变更范围和是否越界，再读核心调用链，检查异常、权限、状态、并发和数据持久化；用行为测试验证正常、失败和边界场景，最后跑全量测试、构建、配置检查和 diff check。"),
            entry("66. Codex 写错过吗？怎么发现？", "会出现，例如把文档描述当成已实现能力、测试隔离不完整或边界状态处理不一致。我通过源码复核、失败测试、真实响应检查和最小集成验证发现问题，再要求按实际代码修正，而不是只看生成摘要。"),
            entry("67. 现场快速做一个 AI Demo 怎么拆？", "先确认输入、输出和不可做的事；再拆成数据层、模型调用层、结构化校验、状态和接口；先用 mock 跑通最小闭环，再接真实模型；最后补异常、日志和一组可重复测试。先证明主链路，再扩展检索、工具和前端。"),
        ],
    ),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#718096"))
    canvas.drawString(18 * mm, 10 * mm, "CrisisAgent | 趣丸 AI Native 全栈研发实习面试速背稿")
    canvas.drawRightString(192 * mm, 10 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName=FONT, fontSize=22, leading=30,
                           alignment=TA_CENTER, textColor=colors.HexColor("#16324F"), spaceAfter=8)
    subtitle = ParagraphStyle("subtitle", parent=styles["Normal"], fontName=FONT, fontSize=11, leading=18,
                              alignment=TA_CENTER, textColor=colors.HexColor("#4A5568"), spaceAfter=14)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT, fontSize=16, leading=22,
                        textColor=colors.HexColor("#16324F"), spaceBefore=8, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT, fontSize=11.5, leading=17,
                        textColor=colors.HexColor("#1F4E79"), spaceBefore=5, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=FONT, fontSize=9.2, leading=14,
                          textColor=colors.HexColor("#243447"), spaceAfter=4)
    small = ParagraphStyle("small", parent=body, fontSize=8.2, leading=12, textColor=colors.HexColor("#718096"))
    callout = ParagraphStyle("callout", parent=body, fontSize=10, leading=16, leftIndent=8, rightIndent=8,
                             borderColor=colors.HexColor("#B8D8E8"), borderWidth=0.6, borderPadding=7,
                             backColor=colors.HexColor("#F2F8FB"), spaceBefore=5, spaceAfter=9)

    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
                            topMargin=15 * mm, bottomMargin=17 * mm, title="CrisisAgent 趣丸 AI Native 面试速背稿",
                            author="CrisisAgent")
    story = [
        Spacer(1, 15 * mm),
        p("CrisisAgent", title),
        p("趣丸 AI Native 全栈研发实习面试速背稿", subtitle),
        p("适用场景：第一次面试官只看简历，从项目自然追问 Agent、RAG、后端工程和 AI Coding。", callout),
        p("一、先背这一段：项目总纲", h1),
        p("CrisisAgent 是一个面向企业公关、法务和品控团队的证据驱动危机响应工作台。它把人工录入或白名单来源采集的负面舆情，经过清洗、去重和事件归并形成可管理的危机事件，再通过固定的六步 Agent Workflow 完成风险分析、声明初稿、RedTeam 审查、Legal RAG 审核、二次改稿和最终决策。系统重点解决的是高风险生成场景中的事实不确定、法律依据不足、上下文污染和结果不可追踪问题。它输出的是可审核的声明草稿、Trace 和报告，不是自动发布系统，也不是全网爬虫。", body),
        p("一句话：固定 Workflow 保证安全骨架，Agent 负责每一步的理解和生成，RAG 提供证据，Human Review 负责高风险兜底，Trace 和 Checkpoint 保证可追踪和可恢复。", callout),
        p("二、万能回答结构", h1),
        p("遇到陌生追问时，按这五句组织：第一，说明业务问题；第二，说明数据从哪里来；第三，说明主链路怎么跑；第四，说明你亲自负责什么；第五，说明系统边界和验证方式。不要把 mock 验证说成生产效果，不要把建议方案说成已完成能力。", body),
        p("三、项目中最容易说错的边界", h1),
        p("1. 五类业务角色、六个流程步骤，因为 Writer 执行两次。\n2. Retrieval Gate 判断要不要查，Evidence Quality Gate 判断查到的能不能信。\n3. ContextPack 是角色化上下文构建和压缩，不只是截断文本。\n4. Harness 是版本化运行策略，不是自动自优化。\n5. 750 passed 是工程回归测试，Eval Center 74/74 是离线案例门槛，两者都不是生产证明。\n6. 项目是生产化思路的工程原型，不要说已经接入真实企业生产系统。", body),
        PageBreak(),
    ]

    for section_name, entries in SECTIONS:
        story.append(p(section_name, h1))
        for question, answer, follow in entries:
            blocks = [p(question, h2), p(answer, body)]
            if follow:
                blocks.append(p("易错边界：" + follow, small))
            story.append(KeepTogether(blocks))
            story.append(Spacer(1, 2))

    story.extend([
        PageBreak(),
        p("七、明天面试前最后背这 10 句", h1),
        p("1. 我做的是证据驱动的企业危机响应 Copilot，不是自动发声明。\n2. 数据先经过清洗、去重、事件归并，再形成 CrisisEvent。\n3. 五类角色对应六步流程，Writer 执行初稿和二稿两次。\n4. 固定的是安全骨架，Agent 在节点内部做受控判断。\n5. AgentState 传递业务结果，Trace 记录过程，Checkpoint 负责恢复。\n6. Retrieval Gate 判断要不要查，Evidence Quality Gate 判断证据能不能信。\n7. 混合检索默认是关键词和向量分数各 0.5，加权后再交给规则型 Reranker。\n8. ContextPack 是按角色整理和压缩的工作材料，不是完整状态。\n9. 真实模型失败可以降级，但必须记录 fallback，不能把失败伪装成成功。\n10. 所有高风险结果最终由 Human Review 把关，Harness 候选必须评测和人工审批后才能启用。", body),
        p("八、最后的诚实声明", h1),
        p("如果面试官问是否上线：目前是具备生产化思路的工程原型，已经验证离线流程、受控采集、工具治理、评测和工作台闭环，但没有包装成已经被企业真实生产使用。下一步重点是真实脱敏数据评测、企业级认证、多租户权限、正式数据库、模型成本监控和运维体系。", callout),
        p("使用建议：先背项目总纲和最后 10 句；再重点复习第 9-17、18-28、29-43、54-67 题。每题回答先讲结论，再讲项目例子，最后主动说边界。", small),
    ])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
