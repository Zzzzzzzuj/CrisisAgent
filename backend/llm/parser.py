import json
import re
import ast

from backend.logger import get_logger


logger = get_logger(__name__)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_PATTERN = re.compile(r",\s*([}\]])")


class LLMParseError(ValueError):
    def __init__(self, message: str, raw_text_preview: str = ""):
        super().__init__(message)
        self.message = message
        self.raw_text_preview = raw_text_preview

    def to_dict(self) -> dict:
        return {
            "error_type": "llm_parse_error",
            "message": self.message,
            "raw_text_preview": self.raw_text_preview,
        }


def parse_json_response(text: str) -> dict:
    cleaned = str(text or "").strip()
    if not cleaned:
        _raise_parse_error("LLM response was empty.", text)

    candidates = [cleaned]
    code_block_match = _CODE_BLOCK_PATTERN.search(cleaned)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    extracted_json = _extract_json_object(cleaned)
    if extracted_json:
        candidates.append(extracted_json)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        _raise_parse_error("LLM JSON output must be an object.", candidate)

    repaired = _repair_json_candidates(candidates)
    for candidate in repaired:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                literal = ast.literal_eval(candidate)
            except (ValueError, SyntaxError):
                continue
            if isinstance(literal, dict):
                return literal
            continue
        if isinstance(parsed, dict):
            logger.info("LLM JSON output parsed after repair.")
            return parsed

    _raise_parse_error("Could not parse JSON object from LLM response.", text)


def validate_required_fields(payload: dict, required_fields: list[str] | tuple[str, ...]) -> dict:
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise LLMParseError(f"Missing required fields: {', '.join(missing)}")
    return payload


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _repair_json_candidates(candidates: list[str]) -> list[str]:
    repaired = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        fixed = _TRAILING_COMMA_PATTERN.sub(r"\1", cleaned)
        fixed = fixed.replace("“", '"').replace("”", '"').replace("’", "'")
        if fixed not in repaired:
            repaired.append(fixed)
    return repaired


def _raise_parse_error(message: str, raw_text) -> None:
    preview = str(raw_text or "")[:200]
    logger.error("LLM JSON parsing failed: %s", message)
    raise LLMParseError(message=message, raw_text_preview=preview)
