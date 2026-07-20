def run(payload: dict) -> dict:
    draft = payload["draft"]
    redteam_review = payload["redteam_review"]
    redteam_suggestions = redteam_review.get("suggestions", [])
    legal_risks = []

    if "确认" in draft or "确实" in draft:
        legal_risks.append("存在在调查完成前直接确认事实的风险。")
    if "一定" in draft or "绝不" in draft:
        legal_risks.append("存在绝对化承诺风险。")
    if "负责到底" in draft:
        legal_risks.append("责任表达过满，可能引发额外法律解释空间。")

    public_opinion_suggestions = []
    for suggestion in redteam_suggestions:
        if "公众" in suggestion or "消费者" in suggestion or "担忧" in suggestion:
            public_opinion_suggestions.append(suggestion)
        elif "核查" in suggestion or "处理承诺" in suggestion:
            public_opinion_suggestions.append(suggestion)

    if not public_opinion_suggestions and redteam_suggestions:
        public_opinion_suggestions = redteam_suggestions[:2]

    integrated_revision_tasks = [
        "保留对公众担忧和消费者不安的明确回应，避免只做程序性表态。",
        "补充核查范围、后续整改和处理动作，但不要提前认定全部事实。",
        "涉及责任时使用条件式表达，例如以核查结果为前提依法依规处理。",
        "避免绝对化承诺，同时让回应看起来不是模板化推责。",
    ]

    return {
        "legal_risks": legal_risks or ["未发现明显高风险承认性表述，但仍需保持条件式措辞。"],
        "safe_points": [
            "使用了核查、配合监管等相对稳妥表达。",
            "未直接下结论认定全部事实成立。",
        ],
        "revision_advice": [
            "保留对事件的重视与歉意，但避免提前定责。",
            "如需提及责任，建议加上核查结果前提。",
            "避免使用绝对化保证性语言。",
        ],
        "public_opinion_suggestions": public_opinion_suggestions,
        "integrated_revision_tasks": integrated_revision_tasks,
        "legal_safety_score_hint": 8,
        "review_summary": "当前草稿整体偏稳妥。结合红队反馈后，建议同时增强公众沟通力度，并继续坚持调查中、配合监管、依法处理的表达方式。",
    }
