import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.tool_reliability import load_cases, run_tool_reliability_eval


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline ToolRunner reliability evaluation.")
    parser.add_argument("--cases", type=Path, default=Path("data/tool_reliability_cases.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = run_tool_reliability_eval(load_cases(args.cases))
    text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if all(item["expected_match"] for item in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
