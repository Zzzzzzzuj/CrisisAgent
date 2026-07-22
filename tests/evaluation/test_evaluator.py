import json
from pathlib import Path

from evaluation import evaluator


def test_load_cases_reads_new_fields(tmp_path: Path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "event": "事件A",
                    "expected_risk": "high",
                    "expected_emotion": "angry",
                    "expected_tone": "先共情、再回应行动、避免抢先定性",
                    "category": "food_safety",
                    "tags": ["标签1", "标签2"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = evaluator.load_cases(cases_path)

    assert len(cases) == 1
    assert cases[0]["category"] == "food_safety"
    assert cases[0]["expected_tone"] == "先共情、再回应行动、避免抢先定性"
    assert cases[0]["tags"] == ["标签1", "标签2"]


def test_summarize_results_includes_tone_and_category_metrics():
    summary = evaluator.summarize_results(
        [
            {
                "id": "case-1",
                "category": "food_safety",
                "risk_match": True,
                "emotion_match": False,
                "tone_match": True,
                "trace_duration_ms": 100,
                "fallback": True,
                "trace": [
                    {
                        "agent": "Agent A",
                        "name": "舆情分析 Agent",
                        "start_time": "2026-07-20T10:00:00+00:00",
                        "end_time": "2026-07-20T10:00:01+00:00",
                        "fallback": False,
                    }
                ],
            },
            {
                "id": "case-2",
                "category": "food_safety",
                "risk_match": False,
                "emotion_match": True,
                "tone_match": False,
                "trace_duration_ms": 300,
                "fallback": False,
                "trace": [
                    {
                        "agent": "Agent A",
                        "name": "舆情分析 Agent",
                        "start_time": "2026-07-20T10:01:00+00:00",
                        "end_time": "2026-07-20T10:01:02+00:00",
                        "fallback": False,
                    }
                ],
            },
        ]
    )

    assert summary["total_cases"] == 2
    assert summary["risk_accuracy"] == 0.5
    assert summary["emotion_accuracy"] == 0.5
    assert summary["tone_accuracy"] == 0.5
    assert summary["category_metrics"]["food_safety"]["total_cases"] == 2
    assert summary["category_metrics"]["food_safety"]["risk_accuracy"] == 0.5
    assert summary["category_metrics"]["food_safety"]["tone_accuracy"] == 0.5


def test_evaluate_case_collects_new_case_fields(monkeypatch):
    fake_response = {
        "session_id": "session-1",
        "final_statement": "statement",
        "scores": {"legal_safety": 8, "empathy": 7, "robustness": 9},
        "agent_trace": [
            {
                "agent": "Agent A",
                "name": "舆情分析 Agent",
                "input": "事件A",
                "output": {
                    "risk_level": "high",
                    "public_emotion": "angry",
                    "keywords": ["曝光"],
                    "recommended_tone": "先共情、再回应行动、避免抢先定性",
                    "analysis_summary": "summary",
                },
                "start_time": "2026-07-20T10:00:00+00:00",
                "end_time": "2026-07-20T10:00:01+00:00",
                "status": "success",
                "mode": "mock",
                "fallback": False,
            }
        ],
    }

    class FakeResult:
        def model_dump(self):
            return fake_response

    monkeypatch.setattr(evaluator, "run_crisis_workflow", lambda request: FakeResult())

    result = evaluator.evaluate_case(
        {
            "id": "case-1",
            "event": "事件A",
            "expected_risk": "high",
            "expected_emotion": "angry",
            "expected_tone": "先共情、再回应行动、避免抢先定性",
            "category": "food_safety",
            "tags": ["标签1"],
        }
    )

    assert result["category"] == "food_safety"
    assert result["tags"] == ["标签1"]
    assert result["predicted_tone"] == "先共情、再回应行动、避免抢先定性"
    assert result["tone_match"] is True
    assert result["final_scores"] == {"legal_safety": 8, "empathy": 7, "robustness": 9}


def test_save_results_generates_compatible_json_and_markdown_reports(tmp_path: Path):
    summary = {
        "total_cases": 1,
        "risk_accuracy": 1.0,
        "emotion_accuracy": 1.0,
        "tone_accuracy": 1.0,
        "fallback_rate": 0.0,
        "average_duration_ms": 120.0,
        "agent_metrics": {
            "Agent A": {
                "agent": "Agent A",
                "name": "舆情分析 Agent",
                "average_duration_ms": 50.0,
                "fallback_count": 0,
                "fallback_rate": 0.0,
                "total_runs": 1,
            }
        },
        "category_metrics": {
            "food_safety": {
                "total_cases": 1,
                "risk_accuracy": 1.0,
                "emotion_accuracy": 1.0,
                "tone_accuracy": 1.0,
                "fallback_rate": 0.0,
                "average_duration_ms": 120.0,
            }
        },
        "case_results": [
            {
                "id": "case-1",
                "event": "事件A",
                "category": "food_safety",
                "tags": ["标签1"],
                "expected_risk": "high",
                "expected_emotion": "angry",
                "expected_tone": "先共情、再回应行动、避免抢先定性",
                "predicted_risk": "high",
                "predicted_emotion": "angry",
                "predicted_tone": "先共情、再回应行动、避免抢先定性",
                "risk_match": True,
                "emotion_match": True,
                "tone_match": True,
                "agent_a_output": {"risk_level": "high"},
                "final_scores": {"legal_safety": 8, "empathy": 7, "robustness": 9},
                "trace": [],
                "trace_duration_ms": 120,
                "fallback_count": 0,
                "fallback": False,
            }
        ],
    }

    saved_paths = evaluator.save_results(
        summary,
        outputs_dir=tmp_path / "outputs",
        reports_dir=tmp_path / "reports",
    )

    json_path = Path(saved_paths["json_path"])
    markdown_path = Path(saved_paths["markdown_path"])

    assert json_path.exists()
    assert markdown_path.exists()

    saved_json = json.loads(json_path.read_text(encoding="utf-8"))
    saved_markdown = markdown_path.read_text(encoding="utf-8")

    assert saved_json["tone_accuracy"] == 1.0
    assert "## Category Metrics" in saved_markdown
    assert "food_safety" in saved_markdown
    assert "PASS" in saved_markdown
