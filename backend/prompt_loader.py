from pathlib import Path
import re


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def load_prompt(name: str, variables: dict | None = None) -> str:
    variables = variables or {}
    prompt_path = PROMPTS_DIR / f"{name}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    template = prompt_path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise KeyError(f"Missing prompt variable: {key}")
        return str(variables[key])

    return _PLACEHOLDER_PATTERN.sub(replace, template)
