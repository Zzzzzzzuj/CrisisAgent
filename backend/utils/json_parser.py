import json
import re

from backend.logger import get_logger


logger = get_logger(__name__)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _error_result(error_type: str, message: str, text: str) -> dict:
    logger.error("JSON parsing failed: %s - %s", error_type, message)
    return {
        "error_type": error_type,
        "message": message,
        "raw_text_preview": text[:200],
    }


def _extract_braced_json(text: str) -> str | None:
    start_positions = [index for index in (text.find("{"), text.find("[")) if index != -1]
    if not start_positions:
        return None

    start = min(start_positions)
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0

    for index in range(start, len(text)):
        char = text[index]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if not cleaned:
        return _error_result("empty_response", "LLM response was empty.", text)

    candidates = [cleaned]

    code_block_match = _CODE_BLOCK_PATTERN.search(cleaned)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    extracted_json = _extract_braced_json(cleaned)
    if extracted_json:
        candidates.append(extracted_json.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        return _error_result("invalid_json_type", "LLM JSON output must be an object.", candidate)

    return _error_result(
        "json_decode_error",
        "Could not parse a JSON object from the LLM response.",
        text,
    )
