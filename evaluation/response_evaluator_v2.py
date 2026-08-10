import json
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.schemas import CrisisRunRequest
from backend.workflow import run_crisis_workflow
from evaluation.response_metrics_v2 import (
    evaluate_response_quality_v2,
    summarize_response_results_v2,
)


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALUATION_DIR / "response_cases_v2.json"
OUTPUTS_DIR = EVALUATION_DIR / "outputs"
REPORTS_DIR = EVALUATION_DIR / "reports"


def load_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(cases_path).read_text(encoding="utf-8"))


def evaluate_case(case: dict, agent_mode: str | None = None) -> dict:
    mode = agent_mode or _get_agent_mode()
    response = run_crisis_workflow(CrisisRunRequest(event=case["event"])).model_dump()
    final_statement = response["final_statement"]
    trace = response["agent_trace"]
    fallback = any(item.get("fallback") for item in trace)
    response_evaluation = evaluate_response_quality_v2(
        final_statement=final_statement,
        event=case["event"],
        case=case,
    )

    return {
        "id": case["id"],
        "split": case["split"],
        "category": case["category"],
        "event": case["event"],
        "expected_risk": case["expected_risk"],
        "expected_emotion": case["expected_emotion"],
        "acceptable_sources": case.get("acceptable_sources", []),
        "required_concepts": case.get("required_concepts", []),
        "expected_actions": case.get("expected_actions", []),
        "forbidden_domain_terms": case.get("forbidden_domain_terms", []),
        "supported_facts": case.get("supported_facts", []),
        "expected_human_review": case.get("expected_human_review"),
        "final_statement": final_statement,
        "workflow_scores": response["scores"],
        "agent_mode": mode,
        "fallback": fallback,
        "response_evaluation_v2": response_evaluation,
        "agent_trace": trace,
    }


def evaluate_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> dict:
    cases = load_cases(cases_path)
    _validate_cases(cases)
    agent_mode = _get_agent_mode()
    case_results = [evaluate_case(case, agent_mode=agent_mode) for case in cases]
    summary = summarize_response_results_v2(case_results)
    summary["agent_mode"] = agent_mode
    summary["case_results"] = case_results
    summary["mock_or_fallback_warning"] = _build_mock_or_fallback_warning(summary)
    return summary


def save_results(
    summary: dict,
    outputs_dir: str | Path = OUTPUTS_DIR,
    reports_dir: str | Path = REPORTS_DIR,
) -> dict:
    outputs_path = Path(outputs_dir)
    reports_path = Path(reports_dir)
    outputs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode = summary.get("agent_mode", "mock")
    json_path = outputs_path / f"response-evaluation-v2-{mode}-{timestamp}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = build_markdown_report(summary)
    markdown_path = reports_path / f"latest_response_report_v2_{mode}.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_markdown_report(summary: dict) -> str:
    average_scores = summary["average_scores"]
    lines = [
        "# CrisisAgent Response Evaluation V2 Report",
        "",
        "## Summary",
        "",
        f"- Agent mode: `{summary.get('agent_mode')}`",
        f"- Total cases: {summary['total_cases']}",
        f"- Pass rate: {summary['pass_rate']}",
        f"- Fallback rate: {summary['fallback_rate']}",
        f"- LLM case count: {summary['llm_case_count']}",
        f"- Mock or fallback case count: {summary['mock_or_fallback_case_count']}",
        f"- Average legal safety: {average_scores['legal_safety']}",
        f"- Average empathy: {average_scores['empathy']}",
        f"- Average action completeness: {average_scores['action_completeness']}",
        f"- Average communication clarity: {average_scores['communication_clarity']}",
        f"- Average hallucination risk: {average_scores['hallucination_risk']}",
        f"- Average domain relevance: {average_scores['domain_relevance']}",
        "",
    ]

    warning = summary.get("mock_or_fallback_warning")
    if warning:
        lines.extend(["## Mock / Fallback Notice", "", warning, ""])

    lines.extend(
        [
            "## Split Summary",
            "",
            "| Split | Total | Pass Rate | Avg Domain Relevance |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for split, metrics in summary.get("split_summary", {}).items():
        lines.append(
            f"| {split} | {metrics['total_cases']} | {metrics['pass_rate']} | "
            f"{metrics['average_domain_relevance']} |"
        )

    lines.extend(
        [
            "",
            "## Category Summary",
            "",
            "| Category | Total | Pass Rate | Avg Domain Relevance |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for category, metrics in summary.get("category_summary", {}).items():
        lines.append(
            f"| {category} | {metrics['total_cases']} | {metrics['pass_rate']} | "
            f"{metrics['average_domain_relevance']} |"
        )

    lines.extend(["", "## Case Details", ""])
    for case in summary.get("case_results", []):
        evaluation = case["response_evaluation_v2"]
        scores = evaluation["scores"]
        result = "PASS" if evaluation["pass"] else "FAIL"
        domain_details = evaluation["details"]["domain_relevance"]
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"- Split: `{case['split']}`",
                f"- Category: `{case['category']}`",
                f"- Result: `{result}`",
                f"- Domain relevance: `{scores['domain_relevance']}`",
                f"- Legal safety: `{scores['legal_safety']}`",
                f"- Empathy: `{scores['empathy']}`",
                f"- Action completeness: `{scores['action_completeness']}`",
                f"- Communication clarity: `{scores['communication_clarity']}`",
                f"- Hallucination risk: `{scores['hallucination_risk']}`",
                f"- Forbidden hits: `{', '.join(domain_details['forbidden_domain_term_hits']) or 'None'}`",
                f"- Issues: `{'; '.join(evaluation['issues']) if evaluation['issues'] else 'None'}`",
                "",
                "Final statement:",
                "",
                case["final_statement"],
                "",
            ]
        )

    return "\n".join(lines)


def _validate_cases(cases: list[dict]) -> None:
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("response_cases_v2 contains duplicate case ids.")

    development_ids = {case["id"] for case in cases if case.get("split") == "development"}
    final_ids = {case["id"] for case in cases if case.get("split") == "final"}
    if development_ids & final_ids:
        raise ValueError("development and final case ids must not overlap.")

    categories = {case["category"] for case in cases}
    final_categories = {case["category"] for case in cases if case.get("split") == "final"}
    missing_final_categories = sorted(categories - final_categories)
    if missing_final_categories:
        raise ValueError(
            "Each category must include at least one final case: "
            + ", ".join(missing_final_categories)
        )


def _get_agent_mode() -> str:
    return os.getenv("AGENT_MODE", "mock").strip().lower() or "mock"


def _build_mock_or_fallback_warning(summary: dict) -> str:
    if summary.get("fallback_rate") == 1.0:
        return (
            "本报告验证的是 mock/fallback 链路和 Evaluation 规则，"
            "不能解释为真实 LLM 生成效果。"
        )
    if summary.get("mock_or_fallback_case_count", 0) > 0:
        return (
            "本报告包含 mock 或 fallback case，相关结果不能直接解释为真实 LLM 生成效果。"
        )
    return ""


def main() -> None:
    summary = evaluate_cases()
    saved_paths = save_results(summary)
    print(
        json.dumps(
            {
                "summary": {
                    key: value
                    for key, value in summary.items()
                    if key != "case_results"
                },
                "saved_paths": saved_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
