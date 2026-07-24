import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.schemas import CrisisRunRequest
from backend.workflow import run_crisis_workflow
from evaluation.metrics import (
    calculate_accuracy,
    calculate_average_duration_ms,
    calculate_average_retrieved_sources,
    calculate_fallback_rate,
    calculate_rag_hit_rate,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_rerank_rank_change,
    calculate_average_rerank_gain,
    calculate_source_distribution,
    calculate_trace_duration_ms,
    summarize_agent_metrics,
    summarize_category_metrics,
)


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALUATION_DIR / "cases.json"
OUTPUTS_DIR = EVALUATION_DIR / "outputs"
REPORTS_DIR = EVALUATION_DIR / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "latest_report.md"


def load_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    path = Path(cases_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_agent_a_output(agent_trace: list[dict]) -> dict:
    for item in agent_trace:
        if item["agent"] == "Agent A":
            return item["output"]
    raise ValueError("Agent A output not found in trace.")


def _extract_agent_b_rag(agent_trace: list[dict]) -> dict:
    for item in agent_trace:
        if item["agent"] == "Agent B":
            return item.get("rag") or {
                "enabled": False,
                "hit": False,
                "sources": [],
                "count": 0,
            }
    return {
        "enabled": False,
        "hit": False,
        "sources": [],
        "count": 0,
    }


def evaluate_case(case: dict) -> dict:
    response = run_crisis_workflow(CrisisRunRequest(event=case["event"])).model_dump()
    agent_trace = response["agent_trace"]
    agent_a_output = _extract_agent_a_output(agent_trace)
    agent_b_rag = _extract_agent_b_rag(agent_trace)
    trace_duration_ms = calculate_trace_duration_ms(agent_trace)
    fallback_count = sum(1 for item in agent_trace if item["fallback"])
    expected_sources = case.get("expected_sources", [])
    rerank_rank_change = calculate_rerank_rank_change(
        expected_sources,
        agent_b_rag.get("chunks", []),
    )

    return {
        "id": case["id"],
        "event": case["event"],
        "category": case["category"],
        "tags": case["tags"],
        "expected_risk": case["expected_risk"],
        "expected_emotion": case["expected_emotion"],
        "expected_tone": case["expected_tone"],
        "expected_sources": expected_sources,
        "predicted_risk": agent_a_output["risk_level"],
        "predicted_emotion": agent_a_output["public_emotion"],
        "predicted_tone": agent_a_output["recommended_tone"],
        "risk_match": agent_a_output["risk_level"] == case["expected_risk"],
        "emotion_match": agent_a_output["public_emotion"] == case["expected_emotion"],
        "tone_match": agent_a_output["recommended_tone"] == case["expected_tone"],
        "agent_a_output": agent_a_output,
        "final_scores": response["scores"],
        "trace": response["agent_trace"],
        "trace_duration_ms": trace_duration_ms,
        "fallback_count": fallback_count,
        "fallback": fallback_count > 0,
        "rag_enabled": agent_b_rag.get("enabled", False),
        "rag_hit": agent_b_rag.get("hit", False),
        "rag_sources": agent_b_rag.get("sources", []),
        "rag_source_count": agent_b_rag.get("count", 0),
        "rag_retrieval_type": agent_b_rag.get("retrieval_type"),
        "rag_query": agent_b_rag.get("query", ""),
        "rag_chunks": agent_b_rag.get("chunks", []),
        "rag_scores": agent_b_rag.get("scores", []),
        "rag_rerank_scores": agent_b_rag.get("rerank_scores", []),
        "rerank_enabled": agent_b_rag.get("rerank_enabled", False),
        "recall_at_k": _calculate_case_recall_at_k(expected_sources, agent_b_rag.get("sources", [])),
        "reciprocal_rank": _calculate_case_reciprocal_rank(expected_sources, agent_b_rag.get("sources", [])),
        "before_rank": rerank_rank_change["before_rank"],
        "after_rank": rerank_rank_change["after_rank"],
        "rerank_gain": rerank_rank_change["rerank_gain"],
    }


def _calculate_case_recall_at_k(expected_sources: list[str], retrieved_sources: list[str]) -> float:
    if not expected_sources:
        return 0.0
    hits = set(expected_sources) & set(retrieved_sources)
    return round(len(hits) / len(expected_sources), 4)


def _calculate_case_reciprocal_rank(expected_sources: list[str], retrieved_sources: list[str]) -> float:
    if not expected_sources:
        return 0.0
    expected = set(expected_sources)
    for index, source in enumerate(retrieved_sources, start=1):
        if source in expected:
            return round(1 / index, 4)
    return 0.0


def summarize_results(case_results: list[dict]) -> dict:
    total_cases = len(case_results)
    if total_cases == 0:
        return {
            "total_cases": 0,
            "risk_accuracy": 0.0,
            "emotion_accuracy": 0.0,
            "tone_accuracy": 0.0,
            "fallback_rate": 0.0,
            "average_duration_ms": 0.0,
            "rag_hit_rate": 0.0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "average_rerank_gain": 0.0,
            "average_retrieved_sources": 0.0,
            "source_distribution": {},
            "agent_metrics": {},
            "category_metrics": {},
            "case_results": [],
        }

    return {
        "total_cases": total_cases,
        "risk_accuracy": calculate_accuracy(case_results, "risk_match"),
        "emotion_accuracy": calculate_accuracy(case_results, "emotion_match"),
        "tone_accuracy": calculate_accuracy(case_results, "tone_match"),
        "fallback_rate": calculate_fallback_rate(case_results),
        "average_duration_ms": calculate_average_duration_ms(case_results),
        "rag_hit_rate": calculate_rag_hit_rate(case_results),
        "recall_at_k": calculate_recall_at_k(case_results),
        "mrr": calculate_mrr(case_results),
        "average_rerank_gain": calculate_average_rerank_gain(case_results),
        "average_retrieved_sources": calculate_average_retrieved_sources(case_results),
        "source_distribution": calculate_source_distribution(case_results),
        "agent_metrics": summarize_agent_metrics(case_results),
        "category_metrics": summarize_category_metrics(case_results),
        "case_results": case_results,
    }


def _build_markdown_report(summary: dict) -> str:
    lines = [
        "# CrisisAgent Evaluation Report",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Risk accuracy: {summary['risk_accuracy']}",
        f"- Emotion accuracy: {summary['emotion_accuracy']}",
        f"- Tone accuracy: {summary['tone_accuracy']}",
        f"- Fallback rate: {summary['fallback_rate']}",
        f"- Average duration: {summary['average_duration_ms']} ms",
        f"- RAG hit rate: {summary['rag_hit_rate']}",
        f"- Recall@K: {summary['recall_at_k']}",
        f"- MRR: {summary['mrr']}",
        f"- Average rerank gain: {summary['average_rerank_gain']}",
        f"- Average retrieved sources: {summary['average_retrieved_sources']}",
        "",
        "## RAG Evaluation",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| RAG Hit Rate | {summary['rag_hit_rate']} |",
        f"| Recall@K | {summary['recall_at_k']} |",
        f"| MRR | {summary['mrr']} |",
        f"| Average Rerank Gain | {summary['average_rerank_gain']} |",
        f"| Average Retrieved Sources | {summary['average_retrieved_sources']} |",
        "",
        "## RAG Source Distribution",
        "",
        "| Source | Count |",
        "| --- | ---: |",
    ]

    for source, count in summary["source_distribution"].items():
        lines.append(f"| {source} | {count} |")

    lines.extend(
        [
            "",
        "## Agent Metrics",
        "",
        "| Agent | Name | Avg Duration (ms) | Fallback Count | Fallback Rate | Total Runs |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for metrics in summary["agent_metrics"].values():
        lines.append(
            f"| {metrics['agent']} | {metrics['name']} | {metrics['average_duration_ms']} | "
            f"{metrics['fallback_count']} | {metrics['fallback_rate']} | {metrics['total_runs']} |"
        )

    lines.extend(
        [
            "",
            "## Category Metrics",
            "",
            "| Category | Total Cases | Risk Accuracy | Emotion Accuracy | Tone Accuracy | Fallback Rate | Avg Duration (ms) | RAG Hit Rate | Recall@K | MRR | Avg Rerank Gain | Avg Sources |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for category, metrics in summary["category_metrics"].items():
        lines.append(
            f"| {category} | {metrics['total_cases']} | {metrics['risk_accuracy']} | "
            f"{metrics['emotion_accuracy']} | {metrics['tone_accuracy']} | "
            f"{metrics['fallback_rate']} | {metrics['average_duration_ms']} | "
            f"{metrics['rag_hit_rate']} | {metrics['recall_at_k']} | {metrics['mrr']} | "
            f"{metrics['average_rerank_gain']} | {metrics['average_retrieved_sources']} |"
        )

    lines.extend(["", "## Case Details", ""])

    for case in summary["case_results"]:
        overall_pass = case["risk_match"] and case["emotion_match"] and case["tone_match"]
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"- Category: `{case['category']}`",
                f"- Tags: `{', '.join(case['tags'])}`",
                f"- Event: {case['event']}",
                f"- Expected risk: `{case['expected_risk']}`",
                f"- Actual risk: `{case['predicted_risk']}`",
                f"- Expected emotion: `{case['expected_emotion']}`",
                f"- Actual emotion: `{case['predicted_emotion']}`",
                f"- Expected tone: `{case['expected_tone']}`",
                f"- Actual tone: `{case['predicted_tone']}`",
                f"- Expected sources: `{', '.join(case.get('expected_sources', []))}`",
                f"- RAG hit: `{case.get('rag_hit', False)}`",
                f"- Retrieval type: `{case.get('rag_retrieval_type')}`",
                f"- RAG sources: `{', '.join(case.get('rag_sources', []))}`",
                f"- Recall@K: `{case.get('recall_at_k', 0.0)}`",
                f"- Reciprocal rank: `{case.get('reciprocal_rank', 0.0)}`",
                f"- Rerank before rank: `{case.get('before_rank')}`",
                f"- Rerank after rank: `{case.get('after_rank')}`",
                f"- Rerank gain: `{case.get('rerank_gain', 0)}`",
                f"- Result: {'PASS' if overall_pass else 'FAIL'}",
                f"- Fallback: `{case['fallback']}`",
                f"- Trace duration: `{case['trace_duration_ms']} ms`",
                f"- Final scores: `{json.dumps(case['final_scores'], ensure_ascii=False)}`",
                "",
            ]
        )

    return "\n".join(lines)


def save_results(summary: dict, outputs_dir: str | Path = OUTPUTS_DIR, reports_dir: str | Path = REPORTS_DIR) -> dict:
    outputs_path = Path(outputs_dir)
    reports_path = Path(reports_dir)
    outputs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = outputs_path / f"evaluation-{timestamp}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = _build_markdown_report(summary)
    latest_report_path = reports_path / "latest_report.md"
    latest_report_path.write_text(markdown, encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(latest_report_path),
    }


def evaluate_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> dict:
    cases = load_cases(cases_path)
    case_results = [evaluate_case(case) for case in cases]
    return summarize_results(case_results)


def main() -> None:
    summary = evaluate_cases()
    saved_paths = save_results(summary)
    output = {
        "summary": summary,
        "saved_paths": saved_paths,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
