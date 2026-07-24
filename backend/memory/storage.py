import json
from pathlib import Path

from backend.memory.schemas import MemoryItem


MEMORY_DATA_DIR = Path(__file__).resolve().parent / "data"
MEMORY_FILE = MEMORY_DATA_DIR / "memories.json"


def save_memory(memory: MemoryItem | dict, memory_file: str | Path = MEMORY_FILE) -> dict:
    memories = list_memories(memory_file)
    memory_data = memory.to_dict() if isinstance(memory, MemoryItem) else dict(memory)
    memories = [item for item in memories if item.get("memory_id") != memory_data["memory_id"]]
    memories.append(memory_data)
    _write_memories(memories, memory_file)
    return memory_data


def list_memories(memory_file: str | Path = MEMORY_FILE) -> list[dict]:
    path = Path(memory_file)
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return json.loads(content)


def get_memory(memory_id: str, memory_file: str | Path = MEMORY_FILE) -> dict | None:
    for memory in list_memories(memory_file):
        if memory.get("memory_id") == memory_id:
            return memory
    return None


def _write_memories(memories: list[dict], memory_file: str | Path) -> None:
    path = Path(memory_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memories, ensure_ascii=False, indent=2), encoding="utf-8")
