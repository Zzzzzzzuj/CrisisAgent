def run(event: str) -> dict:
    keywords = []
    if "过期" in event:
        keywords.append("过期原料")
    if "偷拍视频" in event or "视频" in event:
        keywords.append("传播视频")
    if "监管" in event:
        keywords.append("监管介入")
    if "网友" in event:
        keywords.append("公众愤怒")

    risk_level = "high" if any(word in event for word in ["过期", "监管", "爆", "曝光"]) else "medium"
    public_emotion = "angry" if any(word in event for word in ["要求", "曝光", "愤怒", "偷拍视频"]) else "concerned"
    recommended_tone = "先共情、再回应行动、避免抢先定性"

    return {
        "risk_level": risk_level,
        "public_emotion": public_emotion,
        "keywords": keywords or ["舆情扩散"],
        "recommended_tone": recommended_tone,
        "analysis_summary": "当前事件具有较强传播性和监管敏感性，回应应强调重视、调查、整改与配合监管。",
    }
