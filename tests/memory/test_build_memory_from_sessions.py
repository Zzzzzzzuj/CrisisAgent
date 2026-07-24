import json
from pathlib import Path

from backend.memory.retriever import retrieve_memories
from backend.memory.storage import list_memories
from scripts.build_memory_from_sessions import build_memories_from_sessions, extract_memory


def _session() -> dict:
    return {
        "session_id": "session-1",
        "final_statement": "我们已注意到食品安全相关反馈，并启动专项核查，配合监管调查。",
        "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8},
        "agent_trace": [
            {
                "agent": "Agent A",
                "input": "某食品品牌被爆使用过期原料，网友要求监管介入。",
                "output": {
                    "risk_level": "high",
                    "public_emotion": "angry",
                    "keywords": ["过期原料", "监管介入"],
                },
            },
            {
                "agent": "Agent D",
                "output": {
                    "issues": ["公众可能质疑回应模板化。"],
                    "suggestions": ["补充核查范围和后续处理承诺。"],
                },
            },
            {
                "agent": "Agent B",
                "output": {
                    "legal_risks": ["避免提前确认违法事实。"],
                    "revision_advice": ["使用条件式责任表达。"],
                    "integrated_revision_tasks": ["如核查发现问题，将依法依规处理。"],
                    "public_opinion_suggestions": ["更明确回应消费者担忧。"],
                },
            },
            {
                "agent": "Agent C",
                "output": {
                    "strategy": "先共情，再说明核查、整改和监管配合。",
                },
            },
            {
                "agent": "Agent E",
                "output": {
                    "final_statement": "我们已注意到相关情况，并启动专项核查。",
                    "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8},
                },
            },
        ],
    }


def test_extract_memory_from_session_generates_memory_item():
    memory = extract_memory(_session())
    memory_data = memory.to_dict()

    assert memory_data["memory_id"] == "session-1"
    assert memory_data["category"] == "food_safety"
    assert memory_data["risk_level"] == "high"
    assert memory_data["public_emotion"] == "angry"
    assert memory_data["successful_strategy"] == "先共情，再说明核查、整改和监管配合。"


def test_extracted_memory_fields_are_complete():
    memory_data = extract_memory(_session()).to_dict()

    expected_fields = {
        "memory_id",
        "event_summary",
        "category",
        "risk_level",
        "public_emotion",
        "successful_strategy",
        "legal_lessons",
        "public_opinion_lessons",
        "final_statement_preview",
        "scores",
        "tags",
        "created_at",
    }
    assert set(memory_data.keys()) == expected_fields
    assert "避免提前确认违法事实。" in memory_data["legal_lessons"]
    assert "公众可能质疑回应模板化。" in memory_data["public_opinion_lessons"]
    assert memory_data["scores"] == {"legal_safety": 8, "empathy": 8, "robustness": 8}


def test_build_memories_saves_and_retriever_can_recall(tmp_path: Path):
    session_file = tmp_path / "sessions.json"
    memory_file = tmp_path / "memories.json"
    session_file.write_text(json.dumps([_session()], ensure_ascii=False), encoding="utf-8")

    saved = build_memories_from_sessions(session_file, memory_file)
    memories = list_memories(memory_file)
    retrieval = retrieve_memories("食品品牌过期原料监管介入", top_k=1, memory_file=memory_file)

    assert len(saved) == 1
    assert len(memories) == 1
    assert retrieval["memories"]
    assert retrieval["memories"][0]["memory_id"] == "session-1"
