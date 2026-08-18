import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.core.dynamic_runtime import run_dynamic_agent
from backend.core.guardrail_runtime import apply_guardrails_to_state
from backend.core.state import AgentState
from backend.evaluation.evaluator import evaluate_agent_run
from backend.agents import (
    decision_agent,
    legal_agent,
    redteam_agent,
    sentiment_agent,
    writer_agent,
)


DEFAULT_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。"


def main() -> None:
    event = os.getenv("RAG_ABLATION_EVENT", DEFAULT_EVENT)
    without_rag = _run_case(event, rag_enabled=False)
    with_rag = _run_case(event, rag_enabled=True)
    report = {
        "event": event,
        "rag_disabled": without_rag,
        "rag_enabled": with_rag,
        "comparison": {
            "final_statement_changed": without_rag["final_statement"] != with_rag["final_statement"],
            "legal_risks_changed": without_rag["legal_risks"] != with_rag["legal_risks"],
            "safe_points_changed": without_rag["safe_points"] != with_rag["safe_points"],
            "evaluation_score_delta": {
                "legal_safety_score": (
                    with_rag["evaluation_scores"]["legal_safety_score"]
                    - without_rag["evaluation_scores"]["legal_safety_score"]
                ),
                "empathy_score": (
                    with_rag["evaluation_scores"]["empathy_score"]
                    - without_rag["evaluation_scores"]["empathy_score"]
                ),
                "robustness_score": (
                    with_rag["evaluation_scores"]["robustness_score"]
                    - without_rag["evaluation_scores"]["robustness_score"]
                ),
            },
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _run_case(event: str, rag_enabled: bool) -> dict:
    with _temporary_env("AGENT_MODE", "mock"), _temporary_env("RAG_ENABLED", "true" if rag_enabled else "false"):
        result = run_dynamic_agent(event, agent_registry=_build_ablation_registry())
    state = AgentState(
        session_id=result["session_id"],
        plan_id=result.get("plan_id", ""),
        event=event,
        results=result.get("results", {}),
        trace=result.get("execution_trace", []),
    )
    apply_guardrails_to_state(state)
    decision = result.get("results", {}).get("decision", {})
    legal = result.get("results", {}).get("legal", {})
    final_statement = decision.get("final_statement", "")
    evaluation = evaluate_agent_run(
        event=event,
        results=result.get("results", {}),
        final_statement=final_statement,
        agent_trace=result.get("execution_trace", []),
    )
    legal_trace = _find_legal_trace(result.get("execution_trace", []))
    rag = legal_trace.get("rag", {}) if legal_trace else {}
    guardrails = state.metadata.get("guardrails", {})
    return {
        "session_id": result["session_id"],
        "final_statement": final_statement,
        "legal_risks": legal.get("legal_risks", []),
        "safe_points": legal.get("safe_points", []),
        "guardrail_triggered": _guardrail_triggered(guardrails),
        "evaluation_scores": {
            "legal_safety_score": evaluation["legal_safety_score"],
            "empathy_score": evaluation["empathy_score"],
            "robustness_score": evaluation["robustness_score"],
            "passed": evaluation["passed"],
        },
        "rag_used": rag.get("rag_used", False),
        "retrieval_backend": rag.get("retrieval_backend", "none"),
        "evidence_chunks_count": len(rag.get("evidence_chunks", [])),
        "evidence_summary": rag.get("evidence_summary", ""),
    }


def _build_ablation_registry() -> dict:
    return {
        "sentiment": sentiment_agent.run,
        "writer": writer_agent.run,
        "redteam": redteam_agent.run,
        "legal": _run_legal_with_rag_metadata,
        "writer_v2": writer_agent.generate_second_draft,
        "decision": decision_agent.run,
    }


def _run_legal_with_rag_metadata(payload: dict) -> dict:
    # Keep the demo offline-safe while still exercising the real RAG retrieval path.
    legal_agent._retrieve_legal_context(payload)
    output = legal_agent._run_mock(payload)
    output["_metadata"] = {"rag": legal_agent.get_last_rag_info()}
    return output


def _find_legal_trace(trace: list[dict]) -> dict:
    for item in trace:
        if item.get("agent") == "legal":
            return item
    return {}


def _guardrail_triggered(guardrails: dict) -> bool:
    return any(
        isinstance(value, dict) and value.get("hit")
        for value in guardrails.values()
    )


@contextmanager
def _temporary_env(name: str, value: str):
    previous = os.getenv(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


if __name__ == "__main__":
    main()
