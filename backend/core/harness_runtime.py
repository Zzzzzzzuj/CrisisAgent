from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from backend.harness.spec import harness_trace_reference


@dataclass(frozen=True)
class HarnessRuntimeContext:
    """Immutable per-run view of the selected HarnessSpec."""

    snapshot: dict[str, Any]
    reference: dict[str, str]

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "HarnessRuntimeContext":
        frozen = deepcopy(spec)
        return cls(snapshot=frozen, reference=harness_trace_reference(frozen))

    def trace_metadata(self) -> dict[str, Any]:
        retrieval = self.snapshot.get("retrieval_policy", {})
        review = self.snapshot.get("review_policy", {})
        tools = self.snapshot.get("skills_tools", {})
        return {
            "harness": deepcopy(self.reference),
            "harness_policy": {
                "retrieval": {
                    "min_score": retrieval.get("min_score"),
                    "min_rerank_score": retrieval.get("min_rerank_score"),
                    "max_context_pollution_rate": retrieval.get("max_context_pollution_rate"),
                    "evidence_gate_human_review": retrieval.get("evidence_gate_human_review", True),
                },
                "review_triggers": deepcopy(review.get("triggers", {})),
                "execution_budget": deepcopy(tools.get("execution_budget", {})),
            },
        }


def get_runtime_context(state) -> HarnessRuntimeContext | None:
    spec = state.metadata.get("harness_spec") if hasattr(state, "metadata") else None
    if not isinstance(spec, dict) or not spec:
        return None
    return HarnessRuntimeContext.from_spec(spec)
