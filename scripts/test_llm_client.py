import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["LLM_API_KEY"] = ""


from backend.llm import LLMClient, parse_json_response, validate_required_fields


def main() -> None:
    client = LLMClient()
    raw_response = client.chat(
        [
            {
                "role": "system",
                "content": "You are a CrisisAgent evaluation assistant.",
            },
            {
                "role": "user",
                "content": "Return a JSON response for LLM client smoke test.",
            },
        ]
    )
    parsed = parse_json_response(raw_response)
    validate_required_fields(parsed, ["mock", "content", "input_preview"])

    print(
        json.dumps(
            {
                "raw_response": raw_response,
                "parsed": parsed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
