def generate_first_draft(payload: dict) -> dict:
    event = payload["event"]
    sentiment = payload["sentiment_analysis"]

    statement = (
        "我们已关注到关于本次事件的网络反馈，对由此引发的公众担忧深表重视。"
        "公司已第一时间启动内部核查程序，对涉及批次、采购与生产环节展开全面排查。"
        "在事实进一步核实前，我们将及时同步调查进展，并积极配合相关监管要求。"
        "对于事件给消费者带来的不安，我们表示诚挚歉意。"
    )

    return {
        "statement": statement,
        "strategy": "快速回应，先表达重视与歉意，再说明核查与配合监管。",
        "tone": sentiment["recommended_tone"],
        "notes": f"基于事件“{event}”生成第一版回应。",
    }


def generate_second_draft(payload: dict) -> dict:
    first_statement = payload["first_draft"]["statement"]
    redteam_review = payload["redteam_review"]
    legal_review = payload["legal_review"]
    integrated_tasks = legal_review.get("integrated_revision_tasks", [])
    public_opinion_suggestions = legal_review.get("public_opinion_suggestions", [])

    statement = (
        "我们已注意到关于此事的相关传播内容，并充分理解公众对此产生的担忧与关切。"
        "公司已立即启动专项核查，对相关原料、生产流程、仓储管理及涉事批次进行全面排查。"
        "如核查发现任何违反食品安全要求的情形，我们将严肃处理并依法依规承担相应责任。"
        "目前，我们正同步配合监管部门开展调查，并将根据核查进展持续对外说明。"
        "对于给消费者和合作伙伴带来的不安，我们再次表示歉意。"
    )

    return {
        "statement": statement,
        "strategy": "优先落实 Legal Agent 整合出的修订任务，再兼顾红队反馈中的高价值舆情建议。",
        "revisions_from_v1": [
            "强化对公众担忧的回应",
            "补充专项核查范围",
            "加入依法依规承担责任的条件式表述",
            "根据红队与合规意见弱化可能被视为推责的措辞",
        ],
        "review_summary": {
            "redteam_focus": redteam_review["attack_summary"],
            "legal_focus": legal_review["review_summary"],
            "integrated_revision_tasks": integrated_tasks,
            "public_opinion_suggestions": public_opinion_suggestions,
            "first_draft_excerpt": first_statement[:80],
        },
    }
