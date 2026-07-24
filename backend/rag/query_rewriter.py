DOMAIN_EXPANSIONS = {
    "food_safety": {
        "triggers": ["食品", "过期", "原料", "生产", "餐饮"],
        "queries": ["食品安全风险", "危机回应", "监管调查", "消费者沟通", "法律责任表达"],
    },
    "legal_risk": {
        "triggers": ["定责", "责任", "违法", "承诺", "赔偿", "合规"],
        "queries": ["避免提前定责", "条件式责任表达", "依法依规处理", "绝对化承诺风险"],
    },
    "public_response": {
        "triggers": ["公众", "网友", "舆情", "传播", "质疑", "担忧"],
        "queries": ["公众担忧回应", "消费者沟通", "持续同步进展", "初次回应规范"],
    },
    "privacy": {
        "triggers": ["隐私", "数据", "用户信息", "泄露", "App"],
        "queries": ["隐私风险回应", "用户数据保护", "整改说明", "事实核查"],
    },
}


def rewrite_query(query: str, max_queries: int = 6) -> list[str]:
    normalized = query.strip()
    if not normalized:
        return []

    rewritten = [normalized]
    for config in DOMAIN_EXPANSIONS.values():
        if any(trigger in normalized for trigger in config["triggers"]):
            rewritten.extend(config["queries"])

    deduped = []
    for item in rewritten:
        if item not in deduped:
            deduped.append(item)

    return deduped[:max_queries]
