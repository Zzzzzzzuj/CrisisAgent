def run(payload: dict) -> dict:
    draft = payload["draft"]
    issues = []

    if "事实进一步核实前" in draft:
        issues.append("可能被解读为企业在拖延表态。")
    if "歉意" in draft and "消费者" in draft:
        pass
    else:
        issues.append("对受影响对象的共情表达不够具体。")
    if "整改" not in draft and "排查" in draft:
        issues.append("只提排查，未说明后续整改与问责动作。")

    suggestions = [
        "更明确表达对消费者担忧的理解。",
        "补充核查范围和后续处理承诺。",
        "避免让公众感觉企业只是程序性回应。",
    ]

    return {
        "issues": issues or ["整体回应稳健，但行动承诺还可更具体。"],
        "attack_summary": "公众和媒体可能质疑回应过于模板化，且对整改与责任表述不够有力。",
        "suggestions": suggestions,
    }
