import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.schemas import CrisisRunRequest
from backend.workflow import run_crisis_workflow
from evaluation.response_judge import evaluate_with_optional_judge
from evaluation.response_metrics import evaluate_response_quality, summarize_response_results


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALUATION_DIR / "response_cases.json"
OUTPUTS_DIR = EVALUATION_DIR / "outputs"
REPORTS_DIR = EVALUATION_DIR / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "latest_response_report.md"


def load_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(cases_path).read_text(encoding="utf-8"))


def evaluate_case(case: dict) -> dict:
    response = run_crisis_workflow(CrisisRunRequest(event=case["event"])).model_dump()
    final_statement = response["final_statement"]
    response_evaluation = evaluate_response_quality(
        final_statement=final_statement,
        event=case["event"],
        case=case,
    )
    judge_evaluation = evaluate_with_optional_judge(
        event=case["event"],
        final_statement=final_statement,
        rule_evaluation=response_evaluation,
    )

    return {
        "id": case["id"],
        "category": case.get("category", "unknown"),
        "event": case["event"],
        "must_include": case.get("must_include", []),
        "must_avoid": case.get("must_avoid", []),
        "expected_actions": case.get("expected_actions", []),
        "final_statement": final_statement,
        "workflow_scores": response["scores"],
        "response_evaluation": response_evaluation,
        "judge_evaluation": judge_evaluation,
        "agent_trace": response["agent_trace"],
    }


def evaluate_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> dict:
    case_results = [evaluate_case(case) for case in load_cases(cases_path)]
    summary = summarize_response_results(case_results)
    summary["judge_summary"] = _summarize_judge_results(case_results)
    summary["case_results"] = case_results
    return summary


def _summarize_judge_results(case_results: list[dict]) -> dict:
    if not case_results:
        return {
            "mode": "rule",
            "fallback_rate": 0.0,
            "average_scores": {},
        }

    judge_results = [item["judge_evaluation"] for item in case_results]
    score_keys = judge_results[0]["scores"].keys()
    return {
        "mode": judge_results[0]["mode"],
        "fallback_rate": round(
            sum(1 for item in judge_results if item.get("fallback")) / len(judge_results),
            4,
        ),
        "average_scores": {
            key: round(sum(item["scores"][key] for item in judge_results) / len(judge_results), 2)
            for key in score_keys
        },
    }


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
    json_path = outputs_path / f"response-evaluation-{timestamp}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = build_markdown_report(summary)
    markdown_path = reports_path / LATEST_REPORT_PATH.name
    markdown_path.write_text(markdown, encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_markdown_report(summary: dict) -> str:
    average_scores = summary["average_scores"]
    judge_summary = summary.get("judge_summary", {})
    judge_scores = judge_summary.get("average_scores", {})
    lines = [
        "# CrisisAgent Response Evaluation Report",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Pass rate: {summary['pass_rate']}",
        f"- Average legal safety: {average_scores['legal_safety']}",
        f"- Average empathy: {average_scores['empathy']}",
        f"- Average action completeness: {average_scores['action_completeness']}",
        f"- Average communication clarity: {average_scores['communication_clarity']}",
        f"- Average hallucination risk: {average_scores['hallucination_risk']}",
        "",
        "## LLM Judge Scores",
        "",
        f"- Judge mode: {judge_summary.get('mode', 'rule')}",
        f"- Judge fallback rate: {judge_summary.get('fallback_rate', 0.0)}",
        f"- Judge legal safety: {judge_scores.get('legal_safety', 0.0)}",
        f"- Judge empathy: {judge_scores.get('empathy', 0.0)}",
        f"- Judge action completeness: {judge_scores.get('action_completeness', 0.0)}",
        f"- Judge communication clarity: {judge_scores.get('communication_clarity', 0.0)}",
        f"- Judge hallucination risk: {judge_scores.get('hallucination_risk', 0.0)}",
        "",
        "## Case Details",
        "",
    ]

    for case in summary.get("case_results", []):
        evaluation = case["response_evaluation"]
        judge_evaluation = case.get("judge_evaluation", {})
        scores = evaluation["scores"]
        judge_case_scores = judge_evaluation.get("scores", {})
        result = "PASS" if evaluation["pass"] else "FAIL"
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"- Category: `{case['category']}`",
                f"- Result: `{result}`",
                f"- Legal safety: `{scores['legal_safety']}`",
                f"- Empathy: `{scores['empathy']}`",
                f"- Action completeness: `{scores['action_completeness']}`",
                f"- Communication clarity: `{scores['communication_clarity']}`",
                f"- Hallucination risk: `{scores['hallucination_risk']}`",
                f"- Issues: `{'; '.join(evaluation['issues']) if evaluation['issues'] else 'None'}`",
                f"- Judge mode: `{judge_evaluation.get('mode', 'rule')}`",
                f"- Judge fallback: `{judge_evaluation.get('fallback', False)}`",
                f"- Judge legal safety: `{judge_case_scores.get('legal_safety', 0)}`",
                f"- Judge empathy: `{judge_case_scores.get('empathy', 0)}`",
                f"- Judge action completeness: `{judge_case_scores.get('action_completeness', 0)}`",
                f"- Judge communication clarity: `{judge_case_scores.get('communication_clarity', 0)}`",
                f"- Judge hallucination risk: `{judge_case_scores.get('hallucination_risk', 0)}`",
                f"- Judge issues: `{'; '.join(judge_evaluation.get('issues', [])) if judge_evaluation.get('issues') else 'None'}`",
                "",
                "Final statement:",
                "",
                case["final_statement"],
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    summary = evaluate_cases()
    saved_paths = save_results(summary)
    print(
        json.dumps(
            {
                "summary": summary,
                "saved_paths": saved_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
