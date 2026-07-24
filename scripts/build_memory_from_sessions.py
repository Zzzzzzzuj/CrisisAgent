import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.memory.schemas import MemoryItem, create_memory_item
from backend.memory.storage import MEMORY_FILE, save_memory


def extract_memory(session: dict) -> MemoryItem:
    trace = session.get("agent_trace", [])
    agent_a_output = _find_agent_output(trace, "Agent A")
    agent_b_output = _find_agent_output(trace, "Agent B")
    agent_d_output = _find_agent_output(trace, "Agent D")
    agent_e_output = _find_agent_output(trace, "Agent E")
    event = _extract_event(session)
    final_statement = session.get("final_statement") or agent_e_output.get("final_statement", "")
    scores = session.get("scores") or agent_e_output.get("scores", {})

    return create_memory_item(
        event_summary=_summarize_event(event),
        category=_infer_category(event, agent_a_output),
        risk_level=str(agent_a_output.get("risk_level", "")),
        public_emotion=str(agent_a_output.get("public_emotion", "")),
        successful_strategy=_extract_successful_strategy(trace, agent_e_output),
        legal_lessons=_extract_legal_lessons(agent_b_output),
        public_opinion_lessons=_extract_public_opinion_lessons(agent_d_output, agent_b_output),
        final_statement_preview=final_statement[:120],
        scores=scores,
        tags=_infer_tags(event, agent_a_output),
        memory_id=session.get("session_id"),
    )


def load_sessions(session_file: str | Path) -> list[dict]:
    data = json.loads(Path(session_file).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "agent_trace" in data:
        return [data]
    if isinstance(data, dict):
        sessions = []
        for session_id, session in data.items():
            if isinstance(session, dict):
                sessions.append({"session_id": session_id, **session})
        return sessions
    raise ValueError("Unsupported session JSON format.")


def build_memories_from_sessions(
    session_file: str | Path,
    memory_file: str | Path = MEMORY_FILE,
) -> list[dict]:
    saved_memories = []
    for session in load_sessions(session_file):
        memory = extract_memory(session)
        saved_memories.append(save_memory(memory, memory_file))
    return saved_memories


def _find_agent_output(trace: list[dict], agent: str) -> dict:
    for item in trace:
        if item.get("agent") == agent:
            output = item.get("output", {})
            return output if isinstance(output, dict) else {}
    return {}


def _extract_event(session: dict) -> str:
    for item in session.get("agent_trace", []):
        if item.get("agent") == "Agent A":
            agent_input = item.get("input", "")
            if isinstance(agent_input, str):
                return agent_input
    return str(session.get("event", ""))


def _summarize_event(event: str) -> str:
    return event[:120]


def _infer_category(event: str, agent_a_output: dict) -> str:
    text = f"{event} {' '.join(agent_a_output.get('keywords', []))}"
    if any(keyword in text for keyword in ("食品", "过期原料", "监管")):
        return "food_safety"
    if any(keyword in text for keyword in ("数据", "隐私", "泄露")):
        return "data_security"
    if any(keyword in text for keyword in ("宕机", "服务", "无法上课")):
        return "service_outage"
    if any(keyword in text for keyword in ("高管", "失言", "抵制")):
        return "executive_misconduct"
    return "general_crisis"


def _extract_successful_strategy(trace: list[dict], agent_e_output: dict) -> str:
    for item in reversed(trace):
        if item.get("agent") == "Agent C":
            output = item.get("output", {})
            if isinstance(output, dict) and output.get("strategy"):
                return str(output["strategy"])
    return str(agent_e_output.get("decision_summary", ""))


def _extract_legal_lessons(agent_b_output: dict) -> list[str]:
    lessons = []
    for field in ("legal_risks", "revision_advice", "integrated_revision_tasks"):
        lessons.extend(_as_string_list(agent_b_output.get(field, [])))
    return _dedupe(lessons)


def _extract_public_opinion_lessons(agent_d_output: dict, agent_b_output: dict) -> list[str]:
    lessons = []
    for field in ("issues", "suggestions"):
        lessons.extend(_as_string_list(agent_d_output.get(field, [])))
    lessons.extend(_as_string_list(agent_b_output.get("public_opinion_suggestions", [])))
    return _dedupe(lessons)


def _infer_tags(event: str, agent_a_output: dict) -> list[str]:
    tags = []
    tags.extend(_as_string_list(agent_a_output.get("keywords", [])))
    for keyword in ("食品安全", "过期原料", "监管", "数据泄露", "隐私", "服务中断", "高管失言"):
        if keyword in event:
            tags.append(keyword)
    return _dedupe(tags)


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _dedupe(items: list[str]) -> list[str]:
    deduped = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CrisisAgent memories from session JSON.")
    parser.add_argument("session_file", help="Path to a session JSON file.")
    parser.add_argument("--memory-file", default=str(MEMORY_FILE), help="Path to memories.json.")
    args = parser.parse_args()

    saved_memories = build_memories_from_sessions(args.session_file, args.memory_file)
    print(json.dumps({"saved_count": len(saved_memories), "memories": saved_memories}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
