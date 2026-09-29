from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "CrisisAgent_AI_Native_Interview_Quickbook.pdf"
FONT = r"C:\Windows\Fonts\simhei.ttf"


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E3EE"))
    canvas.line(1.7 * cm, 1.45 * cm, A4[0] - 1.7 * cm, 1.45 * cm)
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(colors.HexColor("#6B7A90"))
    canvas.drawString(1.7 * cm, 0.95 * cm, "CrisisAgent | AI Native 面试速背册 | 仅按项目当前实现口径回答")
    canvas.drawRightString(A4[0] - 1.7 * cm, 0.95 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def build():
    pdfmetrics.registerFont(TTFont("SimHei", FONT))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = A4
    frame = Frame(1.7 * cm, 1.75 * cm, page_w - 3.4 * cm, page_h - 3.35 * cm, id="main")
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm,
        topMargin=1.6 * cm, bottomMargin=1.75 * cm,
        pageTemplates=[PageTemplate(id="body", frames=[frame], onPage=footer)],
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleCN", parent=styles["Title"], fontName="SimHei", fontSize=25,
                           leading=34, textColor=colors.HexColor("#123047"), alignment=TA_CENTER, spaceAfter=10)
    subtitle = ParagraphStyle("SubtitleCN", parent=styles["Normal"], fontName="SimHei", fontSize=10.5,
                              leading=17, textColor=colors.HexColor("#567087"), alignment=TA_CENTER, spaceAfter=18)
    h1 = ParagraphStyle("H1CN", parent=styles["Heading1"], fontName="SimHei", fontSize=17, leading=25,
                        textColor=colors.HexColor("#0F4C5C"), spaceBefore=11, spaceAfter=9)
    h2 = ParagraphStyle("H2CN", parent=styles["Heading2"], fontName="SimHei", fontSize=13, leading=20,
                        textColor=colors.HexColor("#1C6E8C"), spaceBefore=9, spaceAfter=6)
    body = ParagraphStyle("BodyCN", parent=styles["BodyText"], fontName="SimHei", fontSize=9.5, leading=16,
                          textColor=colors.HexColor("#1F2937"), spaceAfter=6)
    small = ParagraphStyle("SmallCN", parent=body, fontSize=8.8, leading=14, textColor=colors.HexColor("#445468"))
    quote = ParagraphStyle("QuoteCN", parent=body, fontName="SimHei", fontSize=10.2, leading=17,
                           textColor=colors.HexColor("#123047"), leftIndent=10, rightIndent=10, spaceBefore=4, spaceAfter=8)
    label = ParagraphStyle("LabelCN", parent=body, fontName="SimHei", fontSize=9, leading=14,
                           textColor=colors.white, alignment=TA_LEFT)

    story = []

    def p(text, style=body):
        story.append(Paragraph(esc(text).replace("\n", "<br/>"), style))

    def section(text):
        story.append(Paragraph(esc(text), h1))

    def sub(text):
        story.append(Paragraph(esc(text), h2))

    def callout(title_text, content, color="#EAF4F7"):
        data = [[Paragraph(esc(title_text), label)], [Paragraph(esc(content).replace("\n", "<br/>"), quote)]]
        table = Table(data, colWidths=[page_w - 3.4 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C6E8C")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(color)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8D5DF")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(Spacer(1, 3))
        story.append(table)
        story.append(Spacer(1, 7))

    def qa(question, answer, risk=None):
        sub("问：" + question)
        p(answer)
        if risk:
            p("真实边界：" + risk, small)

    story.append(Spacer(1, 2.0 * cm))
    story.append(Paragraph("CrisisAgent", title))
    story.append(Paragraph("AI Native 全栈研发实习生面试速背册", title))
    story.append(Paragraph("项目真实实现口径 | 适合 1 分钟介绍、项目深挖与工程追问", subtitle))
    callout("使用方法", "先背第 1 部分的“万能主线”。面试官追问时，再从后面对应模块补 2 到 4 句。不要把离线评测说成线上生产效果，也不要把人工审核说成自动发布。")
    p("你的项目定位：面向企业 PR、法务和品控团队的“证据驱动危机响应 Copilot”。它不是全网爬虫，不是自动发公关稿系统，也不是一次性大模型聊天 Demo。", body)
    story.append(PageBreak())

    section("一、先背这一段：1 分钟项目总述")
    callout("可直接回答", "我做的 CrisisAgent 是一个面向企业负面舆情场景的危机响应工作台。它解决的问题是：企业遇到食品安全、产品质量、数据隐私等争议时，直接让一个大模型写声明，容易出现事实误判、过度承诺和法律风险。\n\n系统前面支持人工录入或白名单来源采集，数据先清洗、去重和事件聚类，形成可管理的 CrisisEvent。之后进入固定六步流程：情感和风险分析、Writer 初稿、RedTeam 审查、Legal RAG 审核、Writer V2 二次改稿和 Decision 决策。系统根据证据质量、来源冲突和审核策略决定是否进入人工审核，最终输出的是声明草稿、审核意见、Trace 和报告，不会自动发布。\n\n我主要负责 Legal RAG 的检索门控、关键词和向量混合检索、重排序和证据质量检查，以及角色化 ContextPack、Harness 受控迭代和离线评测。")
    sub("一句话链路")
    p("人工输入 / 白名单 RSS、GDELT、NewsAPI / 本地数据 → 清洗、去重、聚类 → CrisisEvent → 六步 Agent → Human Review → Trace、报告、评测。")
    sub("一定要主动说的边界")
    p("当前默认路径是离线、mock、JSON 存储和 hash 向量；BGE、真实 LLM、Redis/RQ、PostgreSQL 和手动联网采集是可选路径。项目是具备生产化思路的工程原型，不是已上线生产 SaaS。")

    section("二、Agent、Workflow、State、Skill：一条万能主线")
    qa("为什么 Multi-Agent，而不是一个模型加一个大 Prompt？", "因为危机响应里有明确但不同的职责：风险研判、写稿、挑漏洞、法律审核、最终决策。拆开后，每一步输入输出更清楚，问题能定位到具体环节，后续优化也不会牵动全部流程。它不是为了堆 Agent 数量，而是把高风险声明生成拆成可审查的职责链。")
    qa("为什么固定六步，而不是让模型动态规划？", "固定的是安全骨架，不是每一步内容。当前事件存在明确依赖：没有初稿就无法 RedTeam，没有 RedTeam 和 Legal 意见就无法二次改稿。固定顺序保证 Legal、RedTeam 等关键环节不会被跳过，也便于 Trace、Checkpoint、评测和人工审核。动态决策发生在每一步内部，例如是否检索、是否转人工、选择哪些受控 Skill。")
    qa("Agent 之间怎么通信？", "Agent 不直接互相聊天，而是通过共享运行状态传递结构化结果。Writer 的初稿写入状态，RedTeam 读取初稿并写入问题和建议，Legal 读取事件、初稿和 RedTeam 结果。Executor 再为下一个 Agent 组装所需输入。Trace 负责记录过程，Checkpoint 负责保存可恢复状态。")
    qa("Skill、Agent、Tool 有什么区别？", "Agent 是完整业务角色，例如 Legal；Skill 是角色可复用的一项专业能力，例如证据核验；Tool 是底层可执行函数或接口。当前项目用规则化 Selector 按 Agent 白名单选择 Skill，再通过 ToolRunner 做输入输出校验、超时、重试、预算和 Trace。LLM 不能自由调用任意 Skill。")
    qa("重试、降级、最小安全结果分别是什么？", "重试是在同一路径上再尝试一次，适合临时超时或偶发失败；降级是原路径不可靠时切换到备用或简化路径，例如完整 RAG 管道失败后回退到关键词检索，LLM 调用或 JSON 解析失败后回退 mock。最小安全结果是仍保留事件事实、风险、失败原因和人工审核提示，但不伪造法律依据或自动发布。")
    story.append(PageBreak())

    section("三、RAG：从“要不要查”到“查到的能不能信”")
    qa("为什么 Legal Agent 不每次都直接检索？", "不是所有任务都需要法律检索。普通润色、客服查询、政策学习如果强行检索，会增加延迟和成本，还可能把无关法规带进上下文。Retrieval Gate 先判断是否存在当前企业危机和处置需求，再决定是否放行 RAG。")
    qa("Retrieval Gate 怎么判断？TPR/TNR 是什么？", "Gate 用规则识别现实负面事件、用户影响、舆情传播、企业处置需求，并区分危机响应、普通查询、内容编辑、政策学习等任务意图。明确危机就检索，明确普通任务就跳过，不确定但存在企业风险时偏召回放行。冻结挑战集上，TPR=19/20=95%，表示真正需要检索的案例大多数没有被漏掉；TNR=17/20=85%，表示不需要检索的普通任务大多数被正确拦截。不能只看 Accuracy，因为漏掉危机和多检索一次的代价不同。")
    qa("为什么关键词加 BGE 向量检索？", "关键词检索擅长法规术语、固定表达和产品名；向量检索擅长用户口语、同义表达和语义相近的问题。项目将两路候选按 chunk_id，缺失时按“来源加正文”去重，默认用 0.5 乘关键词分数加 0.5 乘向量分数得到初始融合分。当前代码没有额外做分数归一化，也不是 RRF。")
    qa("Retriever 和 Reranker 有什么区别？", "Retriever 负责从知识库快速扩大候选池；Reranker 负责在有限候选中重新排序。当前 Reranker 是规则型，不是 Cross-Encoder 或 LLM：它结合混合检索分、标题匹配、来源匹配、正文词重合和领域一致性重排，再取 Top-K。不能直接对全库重排，因为成本和延迟会随候选数量上升。")
    qa("Recall@3 不变，为什么还能说 Reranker 有效果？", "Recall@3 只说明正确资料有没有进入前三，不代表前三里有没有混入错误领域资料。项目冻结检索评测中 Recall@3 保持 0.90，但来源类别匹配率从 0.4611 升到 0.6278，上下文污染率从 0.4722 降到 0.3222，说明主要提升是证据纯度和领域匹配，而不是盲目扩大召回。")
    qa("Evidence Quality Gate 为什么还需要？", "Retrieval Gate 判断“要不要查”，Evidence Quality Gate 判断“查到的结果能不能信”。后者检查是否为空、分数和重排分是否过低、来源类别是否不匹配、污染率是否过高、是否发生 fallback。它不重新检索或重排，只把已有证据变成可审计的置信信号。")
    qa("检索执行了但没有可靠证据怎么办？", "不能把“没有证据”理解成“没有法律风险”。系统把证据标记为低置信度，Legal 可以继续输出谨慎意见，但会保留 no_evidence 或低分原因，并由 Human Review Policy 转人工确认。不会自动把声明发布出去。")
    qa("两条法律证据冲突怎么办？", "保留冲突状态和来源，不由模型强行选一条当真。Evidence Quality Gate 标记来源冲突或低置信，Legal 使用条件式表达，Decision 和 Human Review 看到冲突原因后要求人工法务确认。")

    section("四、ContextPack：不是简单截断，而是角色化压缩")
    callout("一段背诵", "ContextPack 是在完整运行状态上做的一层角色化上下文构建和压缩机制。完整状态像案件档案，ContextPack 是给当前 Agent 准备的工作材料。它解决上下文太长、无关信息干扰、未确认信息混入和恢复时上下文漂移的问题。")
    qa("Writer、RedTeam、Legal 分别看到什么？", "Writer 主要看事件事实、公众情绪、历史回应摘要和表达约束，解决“怎么回应”；RedTeam 重点看第一版声明、来源冲突、未确认信息和历史未解决漏洞，解决“哪里会被攻击”；Legal 重点看法律证据、证据置信度、事实状态和法律限制，解决“有没有依据、能不能这样说”。")
    qa("超长时怎么裁？", "先删除低相关和重复内容，再按相关性、风险等级、时间和来源多样性排序。默认限制来源、法律证据、历史案例和人工审核备注的数量，并截断长文本。代码用估算字符数除以 Harness 的预算提示得到使用比例：绿色基本保留，黄色压低重复，橙色减少来源、证据和案例，红色只保留最小安全上下文。")
    qa("怎么避免裁掉关键证据？", "优先保留当前事件事实、风险和事实状态，再保留高相关法律证据；同时记录所有被裁剪内容和原因。如果压缩后证据为空、低分、跨领域或冲突，Evidence Quality Gate 会触发人工审核。当前已有优先级、裁剪记录和质量门控，但还不是“人工标记的关键证据绝对不可裁剪”的强保证，这是可继续补强的边界。")
    qa("为什么要随 Checkpoint 保存 ContextPack？", "避免恢复时上下文漂移。任务第一次运行时使用的证据和历史案例会形成快照；后续即使知识库或 Memory 更新，resume 仍复用原快照，这样同一任务前后依据一致、可复现。")
    story.append(PageBreak())

    section("五、Human Review、Checkpoint、Trace：高风险系统的可控性")
    qa("哪些情况要进入人工审核？", "未确认事实、来源冲突、证据不足或低置信、上下文污染过高、关键工具超时或重试耗尽、审核范围不匹配，以及策略明确要求人工确认时。不是只看风险等级，而是综合证据和运行状态。")
    qa("Checkpoint 是什么？中断后怎么恢复？", "Checkpoint 是一次运行到某一步时的状态快照，保存事件、已经完成的 Agent 结果、Trace、审核状态、Harness 快照和 ContextPack 快照。任务中断时读取该状态，不重复已完成步骤，从未完成节点继续；恢复时仍使用旧 Harness 和旧 ContextPack。")
    qa("Checkpoint 和 Memory 的区别？", "Checkpoint 服务于同一次任务恢复，保存完整运行进度；Memory 服务于跨事件或多轮危机的经验复用，保存的是经过筛选的历史摘要、法律限制和红队问题。Checkpoint 是过程状态，Memory 是长期经验。")
    qa("Trace 记录什么，怎么定位问题？", "Trace 按步骤记录哪个 Agent 执行、输入来源、输出摘要、耗时、RAG 元数据、fallback、ContextPack 引用、Skill 选择和 Harness 版本。出现问题时先看失败在哪个 Agent，再看检索是否跳过、证据质量、工具错误码、是否降级和审核触发原因。")

    section("六、Harness：受控迭代，不是自动自优化")
    qa("Harness Engineering 和 HarnessSpec 是什么？", "Harness Engineering 是给 Agent 外面加运行控制和评测机制。HarnessSpec 是版本化运行策略，记录工具 timeout、retry、预算，检索和证据阈值，上下文策略及审核触发规则。它不允许随意改固定六步顺序、Prompt 主语义或自动发布规则。")
    qa("为什么不把这些写死在代码或 Prompt？", "这些规则需要版本化、对比、追踪和回滚。Prompt 只能指导模型，不能强制工具预算、超时和审核策略。Harness 让每次 Run 保存实际版本和配置快照，方便复现某次结果，并可以把 candidate 与 baseline 在同一批离线 Case 上比较。")
    qa("失败案例如何变成新策略？", "Trace 先生成 failure tag，例如 tool_timeout；诊断模块只建议检查 tools_policy；人工接受 Proposal 后，基于 baseline 复制 DRAFT Candidate，只能改受限字段；Candidate 经 Golden Case 或离线主流程 Replay 对比，检查任务完成率、证据质量、严重失败和工具失败不能变差；最后由人工 APPROVE 后才允许 ACTIVE，发现退步可以 ROLLED_BACK。没有自动改配置、自动审批或自动上线。")

    section("七、效果评测：750 passed 和 Eval Center 74/74 到底说明什么")
    qa("怎么评价 Agent 系统效果？", "不能只看生成文本是否好看。要分层看：工作流和状态是否正确、RAG 是否召回正确领域证据、工具是否稳定、人工审核是否在风险 Case 中触发、声明是否违反事实和法律约束，以及版本迭代是否造成回归。")
    qa("750 passed 和 Eval Center 74/74 分别是什么？", "按简历口径，750 passed 表示单元、接口、集成和安全回归测试通过，证明工程行为没有明显回归；Eval Center 74/74 表示 74 条离线评测 Case 通过既定门槛，例如风险判断、RAG 证据、工具失败、审核触发和 Golden Case。它们不等于真实用户效果，也不等于生产环境已经验证。")
    qa("为什么评测集要冻结？", "如果边调参数边修改同一批评测样本，就会把系统调到“记住答案”，指标会虚高。冻结集固定后，改 RAG、Reranker、Prompt 或 Harness 都要在同一口径下回归比较，才能知道是提升还是回归。")
    qa("项目最大不足和下一步？", "目前仍是工程原型：默认是离线 mock 路径，真实企业数据和长期人工法务评审不足；JSON 存储和本地评测不等同生产数据库和线上 SLA。如果再给两周，我会优先补真实脱敏案例集和人工评审闭环，其次补生产化观测、限流和多租户权限，而不是继续堆 Agent 名词。")
    story.append(PageBreak())

    section("八、工程化：FastAPI、Redis/RQ、Docker、模型稳定性")
    qa("为什么用 Redis-RQ？为什么 FastAPI 不同步跑长任务？", "采集、联网查询或批量归并可能耗时。如果放在 FastAPI 请求线程里，接口会一直阻塞、容易超时，也影响其他用户。Redis 负责队列和任务分发，RQ Worker 在后台消费任务，API 立即返回 queued 或 run_id，前端再轮询状态。")
    qa("Redis 和 RQ 分别做什么？Worker 失败怎么办？", "Redis 是队列和任务状态协调层，RQ 是基于 Redis 的 Python 后台任务框架。业务真相仍保存在 IngestionRun 存储中，不放进 Redis。失败时记录 retry_count、last_error 和心跳；在最大重试次数内重新入队，超过次数进入 dead-letter 状态，供人工检查，不会无限自动重试。")
    qa("重复入队如何考虑幂等？", "核心原则是业务存储是事实来源，任务只是执行尝试。对同一个 run_id 要检查当前状态和任务标识，避免重复创建业务结果；创建 CrisisEvent 时也使用来源 run 加 cluster 的组合做幂等判断。真正生产化时还要增加唯一键、分布式锁和消费幂等记录。")
    qa("Docker 和 Docker Compose 怎么用？", "Docker Image 是打包好的运行环境模板，Container 是基于 Image 启动的运行实例。项目用 Dockerfile 分别构建后端和前端，docker compose 用来统一描述本地 demo 的服务关系；默认路径只启动前后端，PostgreSQL、Redis/RQ 是可选 profile，不应说成默认已经依赖这些服务。")
    qa("FastAPI 和 Pydantic 分别负责什么？", "FastAPI 负责把来源管理、采集、事件、Agent Run、Trace、Review、Report 等能力暴露为 HTTP API；Pydantic 负责请求和响应的字段校验、类型约束和错误返回，避免非法数据直接进入业务流程。")
    qa("模型 API 超时、429、非法 JSON 怎么办？", "超时和 429 属于可重试的临时失败，要使用有上限的 retry 和退避；多次失败后降级为 mock 或返回结构化失败，并保留 Trace。模型输出要求 JSON 时，先提取 JSON、处理常见格式问题，再检查必填字段和类型；仍不合法就不能把坏结果传给下游 Agent，而是走 fallback 或人工审核。")
    qa("新模型怎么接入和 A/B？", "通过统一模型客户端和适配层管理地址、模型名、密钥、超时和返回格式。切换模型不能只改地址，还要验证 JSON 成功率、Tool Calling、上下文、中文法律场景、延迟、Token 成本和异常稳定性。使用相同固定 Case 比较业务效果、结构化输出、证据质量和人工审核覆盖，而不是只看通用排行榜。")

    section("九、舆情采集：从新闻线索到 CrisisEvent")
    qa("Watchlist、RSS、GDELT、NewsAPI 是什么？", "Watchlist 是企业、品牌、产品、别名和风险词的监测配置。RSS 是网站主动提供的订阅源；GDELT 是公开新闻事件和媒体数据查询源；NewsAPI 是新闻搜索 API。三者格式不同，但都要经过受控连接器和统一规范化。")
    qa("不同来源数据怎么统一？", "统一抽取标题、正文摘要、来源、链接、发布时间、查询词和原始标识等公共字段，形成统一的舆情记录。保留来源和时间，不把不同网站的原始结构直接传给下游。")
    qa("两篇新闻怎么判断重复，标题不同怎么聚类？", "先做去重，优先利用 URL、来源标识、标题和时间等确定性信息；标题不同但可能是同一事件时，再用实体、产品、风险词、时间窗口和文本相似性聚成事件簇。聚类后的 CrisisEvent 是一个可管理的危机主题，不等于单篇新闻。")
    qa("不同来源说法冲突、事实未核实怎么办？", "不强行合并成确定事实，而是把 conflict 或 unverified 状态沿着事件、ContextPack、Legal 和 Decision 传递。下游只能用条件式表述，Evidence Gate 和 Human Review 会要求人工确认。")
    qa("为什么真实采集要白名单、timeout 和频率限制？", "因为真实联网有合规和稳定性风险。项目只允许登记来源，RSS 和文章采集遵守 robots，使用 HTTPS、timeout、rate limit 和 max_items；默认关闭 live-fetch，不做递归爬取、登录、验证码绕过、代理池或隐私采集。")
    story.append(PageBreak())

    section("十、AI Native 与 AI Coding：别把 Codex 说成“替我写完了”")
    qa("Prompt 有问题还是模型能力到边界，怎么判断？", "先固定模型、输入和评测 Case，分别检查 Prompt 约束、上下文是否缺失或污染、RAG 证据是否可靠、输出 Schema 是否稳定。如果换 Prompt 后同一模型明显改善，说明 Prompt 或上下文设计有问题；如果多个 Prompt 都无法稳定完成，且证据充分，才可能是模型能力或模型选择问题。")
    qa("temperature 怎么设置？", "高风险结构化判断通常使用较低 temperature，减少格式和结论波动；创作性较强的文案可以略高，但仍要经过 RedTeam 和 Legal 审核。当前项目的 Decision Agent 使用较低 temperature，目的是保持评分和 recommendation 稳定。")
    qa("system prompt 和 user prompt 放什么？", "system prompt 放角色边界、固定安全规则和输出原则；user prompt 放当前事件、证据、声明草稿和本次任务。这样固定规则不会被每次业务数据淹没，动态信息也不会污染系统约束。")
    qa("AI Coding 在项目里怎么用？Codex 帮了什么？", "我把 AI Coding 当成协作工具，用它扫描调用链、生成候选实现、补测试和检查回归；但我自己负责拆解需求、定义安全边界、阅读改动、核对真实运行行为和决定是否采纳。尤其是 RAG 指标、人工审核、权限和降级逻辑，不能因为代码能跑就认为设计正确。")
    qa("AI 生成代码怎么 Review？Codex 写错过怎么办？", "我会先检查它是否改变 API 语义、是否绕过安全策略、是否引入网络或真实模型依赖，再看单测是否只测导入而没有测行为。项目中我遇到过 Windows 上 RQ Worker 默认依赖 os.fork 的问题，消费任务会报错；后来按平台选择 SimpleWorker 或 Worker，并补了选择逻辑测试。这说明 AI 生成或参考的方案必须结合运行环境验证。")
    qa("如果现场快速做 AI Demo，怎么拆？", "先明确输入、输出、失败边界和是否需要人工审核；再拆成最小 API、单一业务流程、mock 模型和固定测试数据；然后补前端展示、Trace 和错误提示。优先证明核心闭环和安全边界，再扩展真实模型、联网、队列和数据库。")

    section("十一、最后 30 秒：万能收尾")
    callout("可直接回答", "我这个项目的核心不是让模型自动发声明，而是把企业舆情处理拆成可控链路：上游把多条线索归并为事件，中间用固定六步 Agent Workflow、Legal RAG、RedTeam 和角色化 ContextPack 生成并审核草稿，下游用 Human Review、Trace、Checkpoint 和报告保证可追踪。对于模型、工具和检索的不确定性，我通过 Gate、结构化校验、重试、降级、预算和离线评测控制风险。当前它仍是离线优先的工程原型，但我刻意把真实落地会需要的数据源、队列、权限、评测和回滚边界设计出来了。面试时先说结论，再给一个项目例子，最后补真实边界。")

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
