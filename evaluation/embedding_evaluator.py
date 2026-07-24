import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.rag.embedding import BGEEmbeddingModel, HashEmbeddingModel
from backend.rag.vector_retriever import VectorRetriever
from evaluation.embedding_metrics import calculate_case_metrics, summarize_embedding_results


EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVALUATION_DIR / "embedding_cases.json"
OUTPUTS_DIR = EVALUATION_DIR / "outputs"
REPORTS_DIR = EVALUATION_DIR / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "latest_embedding_report.md"


def load_cases(cases_path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    return json.loads(Path(cases_path).read_text(encoding="utf-8"))


def build_embedding_model(model_name: str):
    normalized = model_name.strip().lower()
    if normalized == "hash":
        return HashEmbeddingModel()
    if normalized == "bge":
        return BGEEmbeddingModel()
    raise ValueError("Embedding evaluator model must be either 'hash' or 'bge'.")


def evaluate_model(model_name: str, cases: list[dict]) -> dict:
    embedding_model = build_embedding_model(model_name)
    retriever = VectorRetriever(embedding_model=embedding_model)
    case_results = [evaluate_case(case, retriever) for case in cases]
    summary = summarize_embedding_results(case_results)
    return {
        "model": model_name,
        "summary": summary,
        "case_results": case_results,
    }


def evaluate_case(case: dict, retriever: VectorRetriever) -> dict:
    top_k = int(case.get("top_k", 3))
    result = retriever.retrieve(case["query"], top_k=top_k)
    retrieved_sources = [source["source"] for source in result.sources]
    metrics = calculate_case_metrics(case.get("expected_sources", []), retrieved_sources)

    return {
        "id": case["id"],
        "query": case["query"],
        "top_k": top_k,
        "expected_sources": case.get("expected_sources", []),
        "retrieved_sources": retrieved_sources,
        "retrieved_chunks": [chunk.to_dict() for chunk in result.chunks],
        **metrics,
    }


def evaluate_embeddings(
    cases_path: str | Path = DEFAULT_CASES_PATH,
    models: list[str] | None = None,
) -> dict:
    cases = load_cases(cases_path)
    selected_models = models or ["hash", "bge"]
    model_results = [evaluate_model(model, cases) for model in selected_models]

    return {
        "total_cases": len(cases),
        "models": model_results,
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
    json_path = outputs_path / f"embedding-evaluation-{timestamp}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = reports_path / LATEST_REPORT_PATH.name
    markdown_path.write_text(build_markdown_report(summary), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_markdown_report(summary: dict) -> str:
    lines = [
        "# CrisisAgent Embedding Retrieval Evaluation",
        "",
        f"- Total cases: {summary['total_cases']}",
        "",
        "## Model Summary",
        "",
        "| Model | Recall@K | MRR | Average Target Rank |",
        "| --- | ---: | ---: | ---: |",
    ]

    for model_result in summary["models"]:
        metrics = model_result["summary"]
        lines.append(
            f"| {model_result['model']} | {metrics['recall_at_k']} | "
            f"{metrics['mrr']} | {metrics['average_target_rank']} |"
        )

    lines.extend(["", "## Case Details", ""])

    for model_result in summary["models"]:
        lines.extend([f"### {model_result['model']}", ""])
        for case in model_result["case_results"]:
            lines.extend(
                [
                    f"- Case: `{case['id']}`",
                    f"- Query: {case['query']}",
                    f"- Expected sources: `{', '.join(case['expected_sources'])}`",
                    f"- Retrieved sources: `{', '.join(case['retrieved_sources'])}`",
                    f"- Recall@K: `{case['recall_at_k']}`",
                    f"- Reciprocal rank: `{case['reciprocal_rank']}`",
                    f"- Target rank: `{case['target_rank']}`",
                    "",
                ]
            )

    return "\n".join(lines)


def main() -> None:
    summary = evaluate_embeddings()
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
