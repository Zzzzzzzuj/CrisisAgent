"""Run the offline frozen candidate-rule relation baseline."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.legal_claim_relation import evaluate_relation_cases  # noqa: E402


if __name__ == "__main__":
    result = evaluate_relation_cases(ROOT / "data" / "legal_claim_relation_cases.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))
