def run(payload: dict) -> dict:
    statement = payload["second_draft"]
    redteam_review = payload["redteam_review"]
    legal_review = payload["legal_review"]
    sentiment_analysis = payload["sentiment_analysis"]

    legal_safety = max(0, min(10, legal_review.get("legal_safety_score_hint", 7)))
    empathy = 8 if "担忧" in statement and "歉意" in statement else 6
    robustness = 8 if len(redteam_review.get("issues", [])) <= 3 and sentiment_analysis["risk_level"] == "high" else 7

    return {
        "final_statement": statement,
        "scores": {
            "legal_safety": legal_safety,
            "empathy": empathy,
            "robustness": robustness,
        },
        "decision_summary": "第二版在共情、行动说明和法律稳妥性之间取得了更平衡的结果，可作为当前对外回应底稿。",
    }
