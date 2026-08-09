import re

from backend.rag.schemas import RetrievalResult, RetrievedChunk


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
_SOURCE_HINTS = {
    "food": "food_safety.md",
    "食品": "food_safety.md",
    "原料": "food_safety.md",
    "监管": "food_safety.md",
    "legal": "legal_risk_rules.md",
    "法律": "legal_risk_rules.md",
    "定责": "legal_risk_rules.md",
    "责任": "legal_risk_rules.md",
    "危机": "crisis_response.md",
    "回应": "crisis_response.md",
    "舆情": "crisis_response.md",
}


_DOMAIN_SOURCE_HINTS = {
    "food_safety": {"food_safety.md"},
    "data_privacy": {"data_privacy.md"},
    "service_outage": {"service_outage.md"},
    "product_quality": {"product_quality.md"},
    "executive_misconduct": {"executive_misconduct.md"},
}
_DOMAIN_SIGNAL_GROUPS = {
    "food_safety": [
        {"食品", "食用", "餐饮", "糕点", "餐盒", "饮品", "坚果", "冷藏", "异味"},
        {"原料", "过期", "批次", "门店", "试吃", "胃部", "不舒服", "温控"},
    ],
    "data_privacy": [
        {"数据", "隐私", "个人信息", "账号", "手机号", "地址", "订单页", "资料"},
        {"陌生账号", "异常访问", "访问记录", "结算明细", "用户通知", "后台"},
    ],
    "service_outage": [
        {"服务", "系统", "小程序", "页面", "支付", "扣费", "订单", "白屏"},
        {"打不开", "转圈", "恢复", "故障", "排队", "热线", "商户端", "不同步"},
    ],
    "product_quality": [
        {"产品", "质量", "设备", "配件", "充电宝", "耳机", "净水器", "型号"},
        {"鼓起", "发热", "渗水", "松动", "外壳", "充电盒", "检测", "退换"},
    ],
    "executive_misconduct": [
        {"高管", "董事", "负责人", "管理层", "区域负责人", "公开活动", "访谈"},
        {"发言", "表述", "玩笑", "措辞", "录音", "直播", "抵制", "合作方"},
    ],
}
_GENERAL_CRISIS_TERMS = {
    "用户",
    "反馈",
    "说明",
    "客服",
    "检测",
    "问题",
    "回应",
    "处理",
    "安排",
    "统计",
    "准备",
    "确认",
    "原因",
    "平台",
    "团队",
    "品牌",
}
_DOMAIN_MATCH_BONUS = 0.055
_DOMAIN_MISMATCH_PENALTY = -0.11
_DOMAIN_AMBIGUOUS_ADJUSTMENT = 0.0


class RuleBasedReranker:
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 3,
    ) -> RetrievalResult:
        if top_k <= 0 or not chunks:
            return RetrievalResult(context="", chunks=[], sources=[])

        reranked_chunks = [_rerank_chunk(query, chunk) for chunk in chunks]
        reranked_chunks.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
        top_chunks = reranked_chunks[:top_k]

        return RetrievalResult(
            context=_format_context(top_chunks),
            chunks=top_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "rerank_score": chunk.rerank_score,
                }
                for chunk in top_chunks
            ],
        )


def rerank(query: str, chunks: list[RetrievedChunk], top_k: int = 3) -> RetrievalResult:
    return RuleBasedReranker().rerank(query, chunks, top_k)


def _rerank_chunk(query: str, chunk: RetrievedChunk) -> RetrievedChunk:
    title_score = _title_match_score(query, chunk.title)
    source_score = _source_match_score(query, chunk.source)
    overlap_score = _keyword_overlap_score(query, chunk.text)
    query_domains = _infer_domains(query)
    chunk_domains = _infer_domains(
        " ".join([chunk.source, chunk.title, chunk.text]),
        source=chunk.source,
    )
    domain_consistency = _domain_consistency_score(query_domains, chunk_domains)
    domain_adjustment = _domain_adjustment(query_domains, chunk_domains)
    rerank_score = (
        0.48 * chunk.score
        + 0.17 * title_score
        + 0.1 * source_score
        + 0.14 * overlap_score
        + domain_adjustment
    )
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "base_retrieval_score": round(chunk.score, 4),
            "title_match_score": round(title_score, 4),
            "source_match_score": round(source_score, 4),
            "keyword_overlap_score": round(overlap_score, 4),
            "query_domains": sorted(query_domains),
            "chunk_domains": sorted(chunk_domains),
            "domain_consistency": round(domain_consistency, 4),
            "domain_adjustment": round(domain_adjustment, 4),
        }
    )

    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=round(rerank_score, 4),
    )


def _title_match_score(query: str, title: str) -> float:
    return _keyword_overlap_score(query, title)


def _source_match_score(query: str, source: str) -> float:
    for keyword, expected_source in _SOURCE_HINTS.items():
        if keyword in query and expected_source == source:
            return 1.0
    return 0.0


def _infer_domains(text: str, source: str | None = None) -> set[str]:
    tokens = _tokenize(text.lower())
    domains = set()

    if source:
        for domain, sources in _DOMAIN_SOURCE_HINTS.items():
            if source in sources:
                domains.add(domain)

    discriminative_tokens = tokens - _GENERAL_CRISIS_TERMS
    for domain, signal_groups in _DOMAIN_SIGNAL_GROUPS.items():
        matched_groups = 0
        signal_count = 0
        for group in signal_groups:
            matched = group & discriminative_tokens
            if matched:
                matched_groups += 1
                signal_count += len(matched)
        if matched_groups >= 1 and signal_count >= 2:
            domains.add(domain)

    return domains


def _domain_consistency_score(query_domains: set[str], chunk_domains: set[str]) -> float:
    if not query_domains or not chunk_domains:
        return 0.0
    if query_domains & chunk_domains:
        return 1.0
    if len(query_domains) > 1 or len(chunk_domains) > 1:
        return 0.25
    return -1.0


def _domain_adjustment(query_domains: set[str], chunk_domains: set[str]) -> float:
    consistency = _domain_consistency_score(query_domains, chunk_domains)
    if consistency == 1.0:
        return _DOMAIN_MATCH_BONUS
    if consistency == -1.0:
        return _DOMAIN_MISMATCH_PENALTY
    return _DOMAIN_AMBIGUOUS_ADJUSTMENT


def _keyword_overlap_score(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)

    if not query_tokens or not text_tokens:
        return 0.0

    return len(query_tokens & text_tokens) / len(query_tokens)


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for match in _TOKEN_PATTERN.findall(text.lower()):
        tokens.add(match)
        if _contains_chinese(match):
            for index in range(len(match) - 1):
                tokens.add(match[index : index + 2])
    return tokens


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[{chunk.source} | score={chunk.score} | rerank_score={chunk.rerank_score}]\n{chunk.text}"
        )
    return "\n\n".join(context_parts)
