import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = PROJECT_ROOT / "data" / "rag_bad_cases.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "rag_bad_cases_report.md"


def load_bad_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def analyze_bad_cases(cases: list[dict]) -> dict:
    return {
        "total_bad_cases": len(cases),
        "by_failure_type": dict(Counter(case["failure_type"] for case in cases)),
        "by_root_cause": dict(Counter(case["root_cause"] for case in cases)),
        "by_status": dict(Counter(case["status"] for case in cases)),
        "open_cases": [case for case in cases if case["status"] == "open"],
        "suggested_knowledge_updates": _suggest_knowledge_updates(cases),
    }


def write_report(analysis: dict, path: str | Path = DEFAULT_REPORT_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(analysis), encoding="utf-8")


def render_markdown(analysis: dict) -> str:
    lines = [
        "# RAG Bad Cases Report",
        "",
        "This report tracks retrieval failures and suggested knowledge-base updates. It does not call a real LLM.",
        "",
        "## Summary",
        "",
        f"- total_bad_cases: {analysis['total_bad_cases']}",
        f"- by_failure_type: {analysis['by_failure_type']}",
        f"- by_root_cause: {analysis['by_root_cause']}",
        f"- by_status: {analysis['by_status']}",
        "",
        "## Suggested Knowledge Updates",
        "",
    ]
    for item in analysis["suggested_knowledge_updates"]:
        lines.append(f"- `{item['source_category']}`: {item['suggested_fix']}")
    lines.extend(["", "## Open Cases", ""])
    for case in analysis["open_cases"]:
        lines.extend(
            [
                f"### {case['bad_case_id']}",
                "",
                f"- linked_test_case: {case['linked_test_case']}",
                f"- expected_source_category: {case['expected_source_category']}",
                f"- actual_source_category: {case['actual_source_category']}",
                f"- failure_type: {case['failure_type']}",
                f"- root_cause: {case['root_cause']}",
                f"- suggested_fix: {case['suggested_fix']}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    cases = load_bad_cases()
    analysis = analyze_bad_cases(cases)
    write_report(analysis)
    print(json.dumps({k: v for k, v in analysis.items() if k != "open_cases"}, ensure_ascii=False, indent=2))
    print(f"Markdown report: {DEFAULT_REPORT_PATH}")
    return 0


def _suggest_knowledge_updates(cases: list[dict]) -> list[dict]:
    suggestions = {}
    for case in cases:
        if case["status"] != "open":
            continue
        category = case["expected_source_category"]
        if case["root_cause"] == "knowledge_gap" and category not in suggestions:
            suggestions[category] = {
                "source_category": category,
                "suggested_fix": case["suggested_fix"],
            }
    return list(suggestions.values())


if __name__ == "__main__":
    raise SystemExit(main())
