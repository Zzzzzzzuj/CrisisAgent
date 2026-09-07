import json
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.ingestion.deduplicator import deduplicate_items
from backend.ingestion.event_clusterer import cluster_items
from backend.ingestion.normalizer import normalize_item
from backend.ingestion.pipeline import run_sentiment_ingestion_pipeline, to_crisis_event_text
from backend.ingestion.source_adapters import load_local_items


def _run_workflow(
    event_text: str,
    cluster_human_review_required: bool,
    cluster_metadata: dict,
) -> None:
    from backend.core.checkpoint import load_checkpoint
    from backend.core.runtime_tasks import run_dynamic_sync_with_metadata
    from backend.config import get_config
    from backend.llm.config import get_llm_config

    # Set these after backend imports because the database module loads local
    # dotenv files for compatibility with the normal application startup.
    os.environ["AGENT_MODE"] = "mock"
    os.environ["RUNTIME_MODE"] = "sync"
    os.environ["CHECKPOINT_STORAGE"] = "json"
    get_config.cache_clear()
    get_llm_config.cache_clear()

    result = run_dynamic_sync_with_metadata(
        event_text,
        metadata={"ingestion": cluster_metadata},
    )
    saved_state = load_checkpoint(result.get("session_id", ""))
    saved_metadata = (saved_state.metadata if saved_state is not None else {}).get("ingestion", {})
    decision = result.get("results", {}).get("decision", {})
    final_statement = decision.get("final_statement", "")
    trace = result.get("execution_trace", [])
    policy = result.get("policy", {})
    print(json.dumps({
        "workflow_session_id": result.get("session_id"),
        "final_statement_preview": final_statement[:120],
        "scores": decision.get("scores", {}),
        "agents": [item.get("agent") for item in trace if item.get("status") == "success"],
        "cluster_human_review_required": cluster_human_review_required,
        "runtime_policy_required": bool(policy.get("required")),
        "runtime_policy_triggers": policy.get("triggers", []),
        "metadata_ingestion": {
            "source_count": saved_metadata.get("source_count"),
            "event_status": saved_metadata.get("event_status"),
            "fact_status": saved_metadata.get("fact_status"),
            "event_fingerprint": saved_metadata.get("event_fingerprint"),
        },
        "status": result.get("status"),
    }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline sentiment ingestion demo.")
    parser.add_argument(
        "--run-workflow",
        action="store_true",
        help="Run the first high-risk human-review cluster through the mock Dynamic Runtime.",
    )
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "data" / "sentiment_ingestion_fixture.json"
    raw = load_local_items(path)
    normalized = [normalize_item(item) for item in raw]
    deduped, stats = deduplicate_items(normalized)
    clusters = cluster_items(deduped)
    events = run_sentiment_ingestion_pipeline(path)
    print(json.dumps({"raw_count": len(raw), "deduped_count": len(deduped), "cluster_count": len(clusters), "dedup_stats": stats}, ensure_ascii=False))
    for event in events:
        print(json.dumps(event.to_dict(), ensure_ascii=False))
        event_text = to_crisis_event_text(event)
        print("CrisisAgent event:", event_text)
        if args.run_workflow and event.human_review_required and event.risk_level == "high":
            cluster_metadata = event.to_dict()
            _run_workflow(event_text, event.human_review_required, cluster_metadata)
            break


if __name__ == "__main__":
    main()
