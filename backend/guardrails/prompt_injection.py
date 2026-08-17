import re


_PROMPT_INJECTION_PATTERNS = {
    "ignore_instructions": [
        r"ignore (all )?(previous|above) instructions",
        r"忽略(以上|之前|前面).{0,12}(指令|要求|规则)",
        r"不要遵守(以上|之前|系统).{0,12}(指令|要求)",
    ],
    "reveal_system_prompt": [
        r"system prompt",
        r"developer message",
        r"显示.{0,10}(系统提示|提示词|隐藏指令)",
        r"输出.{0,10}(系统提示|提示词|隐藏指令)",
    ],
    "bypass_safety": [
        r"jailbreak",
        r"bypass.{0,20}(safety|guardrail|policy)",
        r"绕过.{0,12}(安全|审核|限制|规则)",
        r"跳过.{0,12}(审核|安全检查|规则)",
    ],
}


def detect_prompt_injection(text: str) -> dict:
    content = str(text or "")
    matched = []
    categories = []

    for category, patterns in _PROMPT_INJECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content, flags=re.IGNORECASE):
                categories.append(category)
                matched.append(pattern)
                break

    hit = bool(categories)
    return {
        "hit": hit,
        "severity": "high" if hit else "none",
        "categories": categories,
        "matched_signals": matched,
        "reason": "prompt_injection_detected" if hit else "",
    }
