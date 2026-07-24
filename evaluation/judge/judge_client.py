from pathlib import Path

from backend.llm_client import call_llm


PROMPT_PATH = Path(__file__).resolve().parent / "judge_prompt.md"


def call_judge_llm(event: str, final_statement: str) -> str:
    prompt = _build_prompt(event, final_statement)
    return call_llm(prompt)


def _build_prompt(event: str, final_statement: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{event}}", event)
        .replace("{{final_statement}}", final_statement)
    )
