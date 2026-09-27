import hashlib
import json
import socket
from copy import deepcopy

import pytest

from evaluation.legal_targeted_paired import (
    DEFAULT_CASES,
    _normalized_kb_hash,
    _validate_frozen_set,
    run_legal_targeted_paired_eval,
)


@pytest.fixture(scope="module")
def report():
    return run_legal_targeted_paired_eval()


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_frozen_kb_hash_ignores_only_newline_style(tmp_path, monkeypatch, newline):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    path = kb_dir / "rule.md"
    path.write_bytes(f"First line{newline}Second line{newline}".encode("utf-8"))
    expected = hashlib.sha256(b"First line\nSecond line\n").hexdigest()
    data = {
        "kb_sha256": {"rule.md": expected},
        "cases": [{
            "case_id": "negative", "label": "negative", "expected_evidence_refs": [],
            "claim": "claim", "event_context": "event", "draft_context": "draft",
            "redteam_context": {},
        }],
    }
    monkeypatch.setattr("evaluation.legal_targeted_paired.load_chunks", lambda _path: [])
    assert _normalized_kb_hash(path) == expected
    assert _validate_frozen_set(data, kb_dir) == set()


@pytest.mark.parametrize("changed", ["First line\nSecond text\n", "First line \nSecond line\n",
                                             "First line\nSecond line!\n"])
def test_frozen_kb_hash_rejects_content_and_whitespace_changes(tmp_path, monkeypatch, changed):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    path = kb_dir / "rule.md"
    path.write_bytes(changed.encode("utf-8"))
    data = {"kb_sha256": {"rule.md": hashlib.sha256(b"First line\nSecond line\n").hexdigest()}}
    monkeypatch.setattr("evaluation.legal_targeted_paired.load_chunks", lambda _path: [])
    with pytest.raises(ValueError, match="Frozen KB changed: rule.md"):
        _validate_frozen_set(data, kb_dir)


def test_frozen_set_and_hash_backend(report):
    assert report["positive_cases"] == 12
    assert report["negative_cases"] == 3
    assert report["configuration"]["embedding"] == "hash-128"
    assert report["configuration"]["vector_backend"] == "json"
    assert report["configuration"]["top_k"] == 3
    assert report["configuration"]["min_rerank_score"] == 0.1


def test_paired_queries_use_same_real_pipeline_and_rewrite(report):
    for case in report["cases"]:
        broad, targeted = case["broad"], case["targeted"]
        assert broad["original_query"].startswith("事件：")
        assert "声明草稿：" in broad["original_query"] and "红队问题：" in broad["original_query"]
        assert targeted["original_query"].startswith(case["claim"])
        assert targeted["original_query"] != broad["original_query"]
        assert broad["pipeline_query_calls"] == broad["rewritten_queries"]
        assert targeted["pipeline_query_calls"] == targeted["rewritten_queries"]
        assert broad["top_k"] == targeted["top_k"] == 3
        for side in (broad, targeted):
            assert all(row["source"] and row["evidence_ref"] and row["score"] is not None
                       and row["rerank_score"] is not None for row in side["results"])


def test_paired_outcomes_and_production_eligibility_are_separate(report):
    assert sum(report["paired_outcome_counts"].values()) == 12
    assert sum(report["p33_eligible_paired_outcome_counts"].values()) == report["p33_eligible_positive_cases"]
    assert report["hit_at_3"]["broad"] == sum(
        row["broad_rank"] is not None for row in report["cases"] if row["label"] == "positive"
    )
    assert report["hit_at_3"]["targeted"] == sum(
        row["targeted_rank"] is not None for row in report["cases"] if row["label"] == "positive"
    )
    for row in report["cases"]:
        if row.get("paired_outcome") == "TARGETED_ONLY":
            assert row["broad_rank"] is None and row["targeted_rank"] is not None
            assert row["p33_eligible_from_broad"] == (
                row["broad"]["p32_recommendation"]["recommended_action"] == "TARGETED_LEGAL_SEARCH"
            )


def test_relation_is_not_conflated_with_retrieval_hit(report):
    for side in ("broad", "targeted"):
        assert sum(report["target_retrieved_relation_coverage"][side].values()) == report["hit_at_3"][side]
    for case in report["cases"]:
        if case["label"] == "negative":
            assert case["expected_evidence_refs"] == []
            assert case["negative_observation"]["broad_candidate_rule_relations"] == 0
            assert case["negative_observation"]["targeted_candidate_rule_relations"] == 0
            assert "targeted_top_rerank_score" in case["negative_observation"]
    assert sum(item["cases"] for item in report["by_material_kind"].values()) == 12


def test_target_only_has_prefilter_and_matched_query_diagnostics(report):
    target_only = [row for row in report["cases"] if row.get("paired_outcome") == "TARGETED_ONLY"]
    for row in target_only:
        assert row["target_in_targeted_candidates"]
        assert row["targeted_target_full_rerank"] is not None
        assert row["targeted_first_recall_kind"] in {
            "original_targeted_query", "shared_rewrite", "targeted_only_rewrite", "unavailable",
        }


def test_results_repeat_without_comparing_wall_clock(report):
    again = run_legal_targeted_paired_eval()
    for first, second in zip(report["cases"], again["cases"]):
        assert first["case_id"] == second["case_id"]
        assert first.get("paired_outcome") == second.get("paired_outcome")
        assert first["rewrite_overlap"] == second["rewrite_overlap"]
        for side in ("broad", "targeted"):
            assert first[side]["results"] == second[side]["results"]
            assert first[side]["relation"] == second[side]["relation"]


def test_changed_expected_ref_or_kb_hash_fails_closed(tmp_path):
    data = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    changed = deepcopy(data)
    changed["cases"][0]["expected_evidence_refs"] = ["missing.md#section-1:chunk-0"]
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Expected evidence"):
        run_legal_targeted_paired_eval(path)
    changed["kb_sha256"]["food_safety.md"] = "0" * 64
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen KB changed"):
        run_legal_targeted_paired_eval(path)


def test_local_evaluation_never_connects_to_network_or_database(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("Network access is forbidden in paired evaluation.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setenv("CHECKPOINT_STORAGE", "postgres")
    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge")
    assert run_legal_targeted_paired_eval()["configuration"]["embedding"] == "hash-128"
