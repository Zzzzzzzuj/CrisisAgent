import argparse
import ast
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_DIRS = (
    "backend/core",
    "backend/rag",
    "backend/agents",
    "backend/skills",
)
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "code_knowledge_index.json"


def build_code_knowledge_index(scan_dirs: tuple[str, ...] = DEFAULT_SCAN_DIRS) -> dict:
    modules = []
    indexed_symbols = 0
    for directory in scan_dirs:
        root = PROJECT_ROOT / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            module = _index_python_file(path)
            indexed_symbols += len(module["classes"]) + len(module["functions"])
            modules.append(module)
    return {
        "summary": {
            "indexed_files": len(modules),
            "indexed_symbols": indexed_symbols,
            "modules": sorted({module["module"] for module in modules}),
        },
        "files": modules,
    }


def write_index(index: dict, output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a static CrisisAgent code knowledge index.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args(argv)
    index = build_code_knowledge_index()
    output_path = write_index(index, args.output)
    print(
        json.dumps(
            {
                "output": str(output_path),
                **index["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _index_python_file(path: Path) -> dict:
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "path": relative_path,
            "module": _module_name(relative_path),
            "responsibility": "syntax_error",
            "classes": [],
            "functions": [],
            "imports": [],
            "error": str(exc),
        }

    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "methods": [
                        child.name
                        for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ],
                    "doc": ast.get_docstring(node) or "",
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "doc": ast.get_docstring(node) or "",
                }
            )

    return {
        "path": relative_path,
        "module": _module_name(relative_path),
        "responsibility": _infer_responsibility(relative_path, source),
        "classes": classes,
        "functions": functions,
        "imports": _extract_imports(tree),
    }


def _module_name(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else ""


def _infer_responsibility(relative_path: str, source: str) -> str:
    path = relative_path.replace("\\", "/")
    lowered = f"{path}\n{source}".lower()
    if "/agents/" in path:
        return "agent implementation and LLM/mock fallback behavior"
    if "dynamic_runtime" in path or "executor" in path or "state" in path:
        return "dynamic runtime, execution orchestration and AgentState management"
    if "checkpoint" in path or "resume" in path:
        return "checkpoint persistence and workflow resume"
    if "/rag/" in path:
        if "retriever" in path:
            return "RAG retrieval, ranking or retrieval backend selection"
        if "knowledge" in path:
            return "knowledge ingestion, governance and document/chunk metadata"
        return "RAG support module"
    if "/skills/" in path:
        return "tool calling, skill registry, MCP mock or A2A schema"
    if "guardrail" in lowered:
        return "guardrail policy and safety checks"
    return "support module"


def _extract_imports(tree: ast.AST) -> list[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
    return sorted(set(imports))


if __name__ == "__main__":
    raise SystemExit(main())
