import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.ingestion.pipeline import run_sentiment_ingestion_items
from backend.ingestion.robots import RobotsChecker
from backend.ingestion.source_adapters import HttpArticleSourceAdapter, RssSourceAdapter
from backend.ingestion.source_registry import SourceRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run explicitly enabled, allowlisted live ingestion.")
    parser.add_argument("--live-fetch", action="store_true", help="Enable network access for registered sources.")
    parser.add_argument("--source-registry", required=True, help="Path to a source registry JSON file.")
    args = parser.parse_args()

    registry = SourceRegistry.from_file(args.source_registry)
    if not args.live_fetch:
        print("Live fetch is disabled. Re-run with --live-fetch to access allowlisted sources.")
        return

    enabled = registry.enabled_sources()
    if not enabled:
        print("No enabled sources. The registry is safe by default; set enabled=true only for an approved source.")
        return

    results = []
    all_items = []
    robots = RobotsChecker()
    for source in enabled:
        adapter = RssSourceAdapter() if source.source_type == "rss" else HttpArticleSourceAdapter()
        result = adapter.fetch(source, robots_checker=robots)
        all_items.extend(result.items)
        results.append({
            "source_id": result.source_id,
            "status": result.status,
            "fetched_count": result.fetched_count,
            "matched_count": result.matched_count,
            "failed_reason": result.failed_reason,
            "items": [{"item_id": item.item_id, "title": item.title, "source_url": item.source_url} for item in result.items],
        })

    events = run_sentiment_ingestion_items(all_items)
    print(json.dumps({
        "live_fetch": True,
        "sources": results,
        "clusters": [
            {"cluster_id": event.cluster_id, "company": event.company, "event_status": event.event_status, "fact_status": event.fact_status, "risk_level": event.risk_level, "human_review_required": event.human_review_required}
            for event in events
        ],
        "automatic_publish": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
