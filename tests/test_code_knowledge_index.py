import json

from scripts.index_project_knowledge import build_code_knowledge_index, main, write_index


def test_code_knowledge_index_contains_core_project_modules():
    index = build_code_knowledge_index()
    modules = set(index["summary"]["modules"])

    assert index["summary"]["indexed_files"] > 0
    assert index["summary"]["indexed_symbols"] > 0
    assert {"backend/core", "backend/rag", "backend/agents", "backend/skills"} <= modules


def test_code_knowledge_index_schema_has_symbols_and_responsibility():
    index = build_code_knowledge_index()
    first_file = index["files"][0]

    assert {
        "path",
        "module",
        "responsibility",
        "classes",
        "functions",
        "imports",
    } <= set(first_file)
    assert any(file["functions"] or file["classes"] for file in index["files"])
    assert any(file["module"] == "backend/skills" for file in index["files"])


def test_write_code_knowledge_index_outputs_json(tmp_path):
    index = build_code_knowledge_index()
    output = tmp_path / "code_knowledge_index.json"

    write_index(index, output)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["summary"]["indexed_files"] == index["summary"]["indexed_files"]


def test_index_project_knowledge_main_can_run_with_custom_output(tmp_path):
    output = tmp_path / "index.json"

    exit_code = main(["--output", str(output)])

    assert exit_code == 0
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert "backend/core" in data["summary"]["modules"]
