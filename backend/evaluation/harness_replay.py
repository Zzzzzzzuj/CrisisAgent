from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from time import sleep
from typing import Any
from uuid import uuid4

from backend.core.executor import execute
from backend.core.harness_runtime import HarnessRuntimeContext
from backend.core.plan_validator import AGENT_ORDER
from backend.core.policy import evaluate_human_policy
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import AgentState
from backend.rag.evidence_quality_gate import evaluate_rag_evidence_quality
from backend.skills.registry import SkillRegistry
from backend.skills.skill_schema import AgentSkill
from backend.skills.tool_runner import ToolRunner
from backend.harness.spec import spec_hash
from backend.harness.policy_guardrails import analyze_policy_diff, evaluate_policy_safety_gate


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = PROJECT_ROOT / "data" / "harness_replay_cases.json"


def load_replay_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Replay case file must contain a cases array.")
    return [case for case in payload["cases"] if isinstance(case, dict)]


class HarnessReplayRunner:
    """Run a deterministic, isolated approximation of the fixed six-agent flow."""

    def __init__(self, harness_spec: dict[str, Any]):
        self.spec = deepcopy(harness_spec)
        self.context = HarnessRuntimeContext.from_spec(self.spec)

    def run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        fixture = case.get("fixture", {})
        state = AgentState(
            session_id=f"replay-{uuid4()}",
            plan_id="replay-fixed-workflow",
            event=str(fixture.get("event", case.get("description", "Replay case"))),
            metadata={
                "harness_spec": deepcopy(self.spec),
                "harness_runtime_context": self.context.trace_metadata(),
                "planner_input": {"category": fixture.get("category", "general"), "risk_level": fixture.get("risk_level", "medium")},
            },
        )
        evidence = deepcopy(fixture.get("evidence", []))
        tool_result = self._run_fake_tool(fixture.get("tool")) if fixture.get("tool") else None
        registry = self._build_fake_agent_registry(evidence, tool_result, fixture)
        plan = {"plan_id": "replay-fixed-workflow", "plan": [{"agent": agent, "reason": "offline replay"} for agent in AGENT_ORDER]}
        execution = execute(plan, state, agent_registry=registry)
        resumed_harness = None
        if fixture.get("checkpoint_resume"):
            resumed = AgentState.from_dict(state.to_dict())
            resumed_harness = HarnessRuntimeContext.from_spec(resumed.metadata["harness_spec"]).trace_metadata()["harness"]
        evaluation = evaluate_runtime_state(state)
        policy = evaluate_human_policy(state, evaluation)
        if fixture.get("review_required") and "review_required" not in policy["triggers"]:
            policy["triggers"].append("review_required")
            policy["required"] = True
        failure_tags = self._failure_tags(evidence, tool_result, policy, fixture)
        expected = case.get("expected", {})
        passed = self._matches_expected(failure_tags, policy, expected)
        return {
            "case_id": str(case.get("case_id", "")),
            "passed": passed,
            "result": "completed" if not policy["required"] and not state.failed_agents else "waiting_human" if policy["required"] else "failed",
            "failure_tags": failure_tags,
            "human_review_required": bool(policy["required"]),
            "policy_triggers": list(policy["triggers"]),
            "policy_decision_accuracy": passed,
            "evidence_quality": self._evidence_quality(evidence, fixture),
            "tool_result": tool_result.to_dict() if tool_result else None,
            "trace": self._trace_summary(state.trace),
            "harness": self.context.trace_metadata()["harness"],
            "harness_policy": self.context.trace_metadata()["harness_policy"],
            "checkpoint_written": False,
            "session_store_written": False,
            "resume_harness": resumed_harness,
            "resume_harness_preserved": resumed_harness == self.context.trace_metadata()["harness"] if resumed_harness else None,
            "expected": deepcopy(expected),
            "execution": {"executed_agents": execution["executed_agents"], "failed_agents": execution["failed_agents"]},
        }

    def _build_fake_agent_registry(self, evidence, tool_result, fixture):
        def sentiment(payload):
            return {"risk_level": fixture.get("risk_level", "medium"), "emotion": "worried", "summary": "offline replay sentiment"}

        def writer(payload):
            return {"statement": "我们正在核查相关情况，并将依法依规处理。"}

        def redteam(payload):
            metadata = {"tool_result": tool_result.to_dict()} if tool_result else {}
            return {"issues": ["offline replay issue"], "suggestions": ["保留事实边界"], "_metadata": metadata}

        def legal(payload):
            quality = evaluate_rag_evidence_quality(
                evidence,
                expected_source_category=payload.get("category"),
                **self._retrieval_policy(),
            )
            return {"legal_risks": [], "safe_points": ["条件式表达"], "revision_advice": [], "public_opinion_suggestions": [], "integrated_revision_tasks": [], "legal_safety_score_hint": 8, "_metadata": {"rag": {"evidence_quality": quality, "chunks": deepcopy(evidence), "retrieval_executed": True, "hit": bool(evidence)}}}

        def writer_v2(payload):
            return {"statement": "我们正在核查相关情况，并将依法依规处理。"}

        def decision(payload):
            return {"final_statement": "离线重放声明草稿", "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8}}

        return {"sentiment": sentiment, "writer": writer, "redteam": redteam, "legal": legal, "writer_v2": writer_v2, "decision": decision}

    def _run_fake_tool(self, tool_fixture):
        if not isinstance(tool_fixture, dict):
            return None
        mode = tool_fixture.get("mode", "success")
        attempts = {"count": 0}

        def handler(payload):
            attempts["count"] += 1
            if mode in {"timeout", "retry"} and attempts["count"] <= int(tool_fixture.get("failures", 1)):
                if mode == "timeout":
                    sleep((self._tool_timeout_ms() + 20) / 1000)
                raise RuntimeError("replay tool failure")
            return {"ok": True}

        definition = AgentSkill(name="replay_tool", description="offline replay tool", input_schema={"type": "object"}, output_schema={"type": "object"}, category="replay", owner_agent="replay", safety_level="low", enabled=True, version="1", handler=handler)
        spec = deepcopy(self.spec)
        tools = spec.setdefault("skills_tools", {})
        definitions = tools.setdefault("definitions", [])
        definition_row = definition.to_dict()
        definition_row["timeout_ms"] = self._tool_timeout_ms()
        definition_row["max_retries"] = self._tool_max_retries(tool_fixture)
        definitions.append(definition_row)
        runner = ToolRunner(SkillRegistry([definition]), harness_spec=spec)
        return runner.run("replay_tool", {})

    def _retrieval_policy(self):
        policy = self.spec.get("retrieval_policy", {})
        return {"min_score": float(policy.get("min_score", 0.1)), "min_rerank_score": float(policy.get("min_rerank_score", 0.1)), "max_context_pollution_rate": float(policy.get("max_context_pollution_rate", 0.5))}

    def _tool_timeout_ms(self):
        return int(self.spec.get("skills_tools", {}).get("timeout_ms", 3000))

    def _tool_max_retries(self, fixture):
        return int(self.spec.get("skills_tools", {}).get("max_retries", fixture.get("max_retries", 0)))

    def _evidence_quality(self, evidence, fixture):
        return evaluate_rag_evidence_quality(evidence, expected_source_category=fixture.get("category"), **self._retrieval_policy())

    @staticmethod
    def _failure_tags(evidence, tool_result, policy, fixture):
        tags = []
        quality = policy.get("_evidence_quality") if isinstance(policy, dict) else None
        if evidence:
            categories = [row.get("source_category") for row in evidence]
            if len(set(categories)) > 1:
                tags.append("evidence_conflict")
        if tool_result and tool_result.error_code:
            mapping = {"TOOL_TIMEOUT": "tool_timeout", "TOOL_RETRY_EXHAUSTED": "tool_retry_exhausted", "TOOL_LOOP_DETECTED": "tool_loop_detected"}
            if tool_result.error_code in mapping:
                tags.append(mapping[tool_result.error_code])
        if any(trigger in policy.get("triggers", []) for trigger in ("rag_evidence_low_confidence", "review_required")):
            tags.append("evidence_low_confidence")
        if fixture.get("context_pollution"):
            tags.append("context_over_budget")
        return list(dict.fromkeys(tags))

    @staticmethod
    def _matches_expected(tags, policy, expected):
        expected_tags = set(expected.get("failure_tags", []))
        return expected_tags.issubset(set(tags)) and bool(policy.get("required")) == bool(expected.get("human_review_required", False))

    @staticmethod
    def _trace_summary(trace):
        return [{"agent": item.get("agent"), "status": item.get("status"), "harness": item.get("harness"), "error": item.get("error")} for item in trace]


def compare_harness_replay(baseline: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else load_replay_cases()
    baseline_runner, candidate_runner = HarnessReplayRunner(baseline), HarnessReplayRunner(candidate)
    baseline_cases = [baseline_runner.run_case(case) for case in cases]
    candidate_cases = [candidate_runner.run_case(case) for case in cases]
    result = {
        "comparison_id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "mode": "main_workflow_replay", "offline_only": True, "case_count": len(cases),
        "baseline": _variant(baseline, baseline_cases), "candidate": _variant(candidate, candidate_cases),
        "delta": _delta(_variant(baseline, baseline_cases)["metrics"], _variant(candidate, candidate_cases)["metrics"]),
        "same_case_ids": [str(case.get("case_id", "")) for case in cases], "automatic_enable": False, "automatic_publish": False,
    }
    result["policy_diff"] = analyze_policy_diff(baseline, candidate)
    result["policy_safety_gate"] = evaluate_policy_safety_gate(result)
    return result


def _variant(spec, items):
    return {"harness_id": spec.get("metadata", {}).get("harness_id"), "version": spec.get("metadata", {}).get("version"), "spec_hash": spec_hash(spec), "metrics": _metrics(items), "cases": items}


def _metrics(items):
    total = len(items)
    tags = {}
    for item in items:
        for tag in item["failure_tags"]:
            tags[tag] = tags.get(tag, 0) + 1
    return {"task_completion_rate": _rate(sum(item["result"] == "completed" for item in items), total), "evidence_quality_rate": _rate(sum(not "evidence_low_confidence" in item["failure_tags"] for item in items), total), "tool_failure_rate": _rate(sum(bool(item.get("tool_result") and not item["tool_result"]["success"]) for item in items), total), "human_review_trigger_rate": _rate(sum(item["human_review_required"] for item in items), total), "policy_decision_accuracy": _rate(sum(item["policy_decision_accuracy"] for item in items), total), "failure_tag_counts": tags}


def _delta(left, right):
    keys = ("task_completion_rate", "evidence_quality_rate", "tool_failure_rate", "human_review_trigger_rate", "policy_decision_accuracy")
    return {key: round(float(right.get(key, 0)) - float(left.get(key, 0)), 4) for key in keys}


def _rate(value, total):
    return round(value / total, 4) if total else 0.0
