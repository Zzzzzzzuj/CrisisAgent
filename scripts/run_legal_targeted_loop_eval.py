"""Print the offline P33 coverage regression baseline."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.legal_targeted_loop import run_legal_targeted_loop_eval


if __name__ == "__main__":
    print(json.dumps(run_legal_targeted_loop_eval(), ensure_ascii=False, indent=2))
