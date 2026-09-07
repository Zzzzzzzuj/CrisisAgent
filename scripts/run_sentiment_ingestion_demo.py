import json
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


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "sentiment_ingestion_fixture.json"
    raw = load_local_items(path)
    normalized = [normalize_item(item) for item in raw]
    deduped, stats = deduplicate_items(normalized)
    clusters = cluster_items(deduped)
    events = run_sentiment_ingestion_pipeline(path)
    print(json.dumps({"raw_count": len(raw), "deduped_count": len(deduped), "cluster_count": len(clusters), "dedup_stats": stats}, ensure_ascii=False))
    for event in events:
        print(json.dumps(event.to_dict(), ensure_ascii=False))
        print("CrisisAgent event:", to_crisis_event_text(event))


if __name__ == "__main__":
    main()
