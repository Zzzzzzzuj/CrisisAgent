import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


os.environ.setdefault("AGENT_MODE", "mock")


from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import AgentState


DEMO_CASES_PATH = PROJECT_ROOT / "demo" / "cases.json"


def main() -> None:
    cases = _load_demo_cases()
    print(f"CrisisAgent Demo Cases: {len(cases)}")
    print("=" * 72)

    for case in cases:
        _run_case(case)
        print("=" * 72)


def _load_demo_cases() -> list[dict]:
    return json.loads(DEMO_CASES_PATH.read_text(encoding="utf-8"))


def _run_case(case: dict) -> None:
    print(f"case: {case['id']} | {case['name']}")
    print(f"event: {case['event']}")
    result = run_dynamic_agent(case["event"])
    state = _state_from_result(result)
    evaluation = evaluate_runtime_state(state)
    policy = evaluate_human_policy(state, evaluation)

    print("\ndynamic runtime result:")
    print(f"- session_id: {result['session_id']}")
    print(f"- plan_id: {result['plan_id']}")
    print(f"- executed_agents: {', '.join(result['executed_agents'])}")
    print(f"- failed_agents: {_format_failed_agents(result['failed_agents'])}")

    print("\nplan:")
    for item in result["validated_plan"]["plan"]:
        print(f"- {item['agent']} | confidence={item.get('confidence', '-')}: {item.get('reason', '')}")

    print("\nagent trace:")
    for item in result["execution_trace"]:
        print(
            f"- {item.get('agent')} | status={item.get('status')} | "
            f"error={item.get('error') or 'none'} | output={_summary(item.get('output'))}"
        )

    print("\nRAG / Memory:")
    print(f"- rag_hit: {_has_hit(result['execution_trace'], 'rag')}")
    print(f"- memory_hit: {_has_hit(result['execution_trace'], 'memory')}")

    print("\nevaluation:")
    print(f"- passed: {evaluation.get('passed')}")
    print(f"- issues: {evaluation.get('issues')}")
    print(f"- quality_scores: {evaluation.get('quality_scores')}")

    print("\nhuman gate:")
    print(f"- required: {policy.get('required')}")
    print(f"- reason: {policy.get('reason') or 'none'}")
    print(f"- triggers: {policy.get('triggers')}")

    print("\nfinal statement:")
    print(_final_statement(result))


def _state_from_result(result: dict) -> AgentState:
    state = AgentState(
        session_id=result["session_id"],
        plan_id=result.get("plan_id", ""),
        event=result.get("event", ""),
        results=result.get("results", {}),
        trace=result.get("execution_trace", []),
        metadata={
            "planner_input": result.get("planner_input", {}),
            "raw_plan": result.get("raw_plan", {}),
            "validated_plan": result.get("validated_plan", {}),
        },
    )
    state.failed_agents = list(result.get("failed_agents", []))
    return state


def _format_failed_agents(failed_agents: list[dict]) -> str:
    if not failed_agents:
        return "none"
    return "; ".join(f"{item.get('agent')}: {item.get('reason')}" for item in failed_agents)


def _has_hit(trace: list[dict], key: str) -> bool:
    return any((item.get(key) or {}).get("hit") for item in trace)


def _final_statement(result: dict) -> str:
    decision = result.get("results", {}).get("decision", {})
    return decision.get("final_statement") or "No final statement generated."


def _summary(value, max_length: int = 120) -> str:
    if value is None:
        return "none"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= max_length else f"{text[:max_length]}..."


if __name__ == "__main__":
    main()
