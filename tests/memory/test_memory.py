from pathlib import Path

from backend.memory.retriever import retrieve_memories
from backend.memory.schemas import create_memory_item
from backend.memory.storage import get_memory, list_memories, save_memory


def _memory(memory_id: str, event_summary: str, category: str, tags: list[str]):
    return create_memory_item(
        memory_id=memory_id,
        event_summary=event_summary,
        category=category,
        risk_level="high",
        public_emotion="angry",
        successful_strategy="先共情，再说明核查和监管配合。",
        legal_lessons=["避免提前定责", "使用条件式责任表达"],
        public_opinion_lessons=["回应消费者担忧", "说明后续处理动作"],
        final_statement_preview="我们已注意到相关情况，并启动专项核查。",
        scores={"legal_safety": 8, "empathy": 8, "robustness": 8},
        tags=tags,
        created_at="2026-07-23T00:00:00+00:00",
    )


def test_save_memory(tmp_path: Path):
    memory_file = tmp_path / "memories.json"
    memory = _memory("memory-1", "食品品牌被曝使用过期原料", "food_safety", ["食品安全"])

    saved = save_memory(memory, memory_file)
    memories = list_memories(memory_file)

    assert saved["memory_id"] == "memory-1"
    assert len(memories) == 1
    assert memories[0]["event_summary"] == "食品品牌被曝使用过期原料"


def test_get_memory_reads_saved_memory(tmp_path: Path):
    memory_file = tmp_path / "memories.json"
    save_memory(_memory("memory-1", "食品安全危机", "food_safety", ["食品安全"]), memory_file)

    result = get_memory("memory-1", memory_file)

    assert result is not None
    assert result["memory_id"] == "memory-1"
    assert result["category"] == "food_safety"


def test_retrieve_memories_returns_similar_history(tmp_path: Path):
    memory_file = tmp_path / "memories.json"
    save_memory(_memory("food-memory", "食品品牌过期原料危机", "food_safety", ["食品安全", "监管"]), memory_file)
    save_memory(_memory("data-memory", "互联网平台数据泄露", "data_security", ["隐私", "数据"]), memory_file)

    result = retrieve_memories("食品品牌被曝过期原料，监管介入", top_k=1, memory_file=memory_file)

    assert result["memories"]
    assert result["memories"][0]["memory_id"] == "food-memory"
    assert "food-memory" in result["context"]


def test_retrieve_memories_handles_empty_store(tmp_path: Path):
    memory_file = tmp_path / "memories.json"

    result = retrieve_memories("食品安全", top_k=3, memory_file=memory_file)

    assert result == {"memories": [], "context": ""}
