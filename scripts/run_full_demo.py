import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.getenv("CRISIS_AGENT_BASE_URL", "http://127.0.0.1:8000")
DEMO_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入。"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["AGENT_MODE"] = "mock"
os.environ["CHECKPOINT_STORAGE"] = "json"
os.environ["RUNTIME_MODE"] = "sync"

from backend.core.dynamic_runtime import run_dynamic_agent


def main() -> None:
    started_at = time.perf_counter()
    summary = []
    print("CrisisAgent Full Demo")
    print("=" * 72)
    print("mode: mock/offline")
    print(f"backend: {BASE_URL}")
    print("tip: for offline demo, start backend with AGENT_MODE=mock and CHECKPOINT_STORAGE=json")
    print("=" * 72)

    summary.append(_run_step("backend health check", _check_health))
    summary.append(_run_step("readiness check", _check_ready))
    summary.append(_run_step("runtime metrics check", _check_runtime_metrics))
    summary.append(_run_step("mock dynamic workflow demo", _run_mock_dynamic_workflow))
    summary.append(_run_step("RAG evidence demo", _run_rag_evidence_demo))
    summary.append(_run_step("RAG ablation demo", _run_rag_ablation_demo))

    passed = sum(1 for item in summary if item["status"] == "passed")
    failed = [item for item in summary if item["status"] == "failed"]

    print("=" * 72)
    print("Demo Summary")
    print(json.dumps(
        {
            "passed": passed,
            "failed": len(failed),
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "steps": summary,
        },
        ensure_ascii=False,
        indent=2,
    ))

    if failed:
        raise SystemExit(1)


def _run_step(name: str, fn) -> dict:
    print(f"\n[{name}]")
    started_at = time.perf_counter()
    try:
        details = fn()
        result = {
            "name": name,
            "status": "passed",
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "details": details,
        }
        print(f"PASS: {json.dumps(details, ensure_ascii=False)}")
        return result
    except Exception as exc:
        result = {
            "name": name,
            "status": "failed",
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "error": str(exc),
        }
        print(f"FAIL: {exc}")
        return result


def _check_health() -> dict:
    data = _get_json("/health")
    return {"status": data.get("status")}


def _check_ready() -> dict:
    data = _get_json("/ready")
    return {
        "ready": data.get("ready"),
        "checkpoint_backend": data.get("checks", {}).get("checkpoint_backend", {}).get("status"),
        "async_runtime": data.get("checks", {}).get("async_runtime", {}).get("status"),
    }


def _check_runtime_metrics() -> dict:
    data = _get_json("/api/metrics/runtime")
    return {
        "total_sessions": data.get("total_sessions", 0),
        "completed_sessions": data.get("completed_sessions", 0),
        "waiting_human_sessions": data.get("waiting_human_sessions", 0),
        "rag_hit_count": data.get("rag_hit_count", 0),
        "llm_fallback_count": data.get("llm_fallback_count", 0),
    }


def _run_mock_dynamic_workflow() -> dict:
    result = run_dynamic_agent(DEMO_EVENT)
    return {
        "session_id": result.get("session_id"),
        "status": result.get("status"),
        "executed_agents": result.get("executed_agents", []),
        "failed_agents": result.get("failed_agents", []),
        "final_statement_present": bool(
            result.get("results", {}).get("decision", {}).get("final_statement")
        ),
    }


def _run_rag_evidence_demo() -> dict:
    from scripts import run_rag_ablation_demo

    result = run_rag_ablation_demo._run_case(DEMO_EVENT, rag_enabled=True)
    return {
        "rag_used": result.get("rag_used"),
        "retrieval_backend": result.get("retrieval_backend"),
        "evidence_chunks_count": result.get("evidence_chunks_count"),
        "evidence_summary": result.get("evidence_summary"),
    }


def _run_rag_ablation_demo() -> dict:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "run_rag_ablation_demo.py")],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "AGENT_MODE": "mock"},
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "RAG ablation demo failed")

    report = json.loads(_extract_json_object(completed.stdout))
    return {
        "rag_disabled_used": report["rag_disabled"]["rag_used"],
        "rag_enabled_used": report["rag_enabled"]["rag_used"],
        "rag_enabled_backend": report["rag_enabled"]["retrieval_backend"],
        "rag_enabled_evidence_chunks": report["rag_enabled"]["evidence_chunks_count"],
    }


def _get_json(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    try:
        with request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{url} returned HTTP {exc.code}: {body}\n{_environment_hint(body)}") from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach {url}. Start backend first: python -m uvicorn backend.main:app --reload"
        ) from exc


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in ablation output.")
    return text[start : end + 1]


def _environment_hint(body: str) -> str:
    normalized = body.lower()
    if "postgres" in normalized or "psycopg" in normalized or "modulenotfounderror" in normalized:
        return (
            "Environment hint: backend appears to be running with CHECKPOINT_STORAGE=postgres. "
            "Install PostgreSQL dependencies with `pip install -r requirements.txt`, verify DATABASE_URL, "
            "run `python -m alembic upgrade head`, or switch to CHECKPOINT_STORAGE=json for offline mock demo."
        )
    return (
        "Environment hint: HTTP checks failed, but local mock dynamic/RAG demos can still run. "
        "Check /ready details, environment variables, and backend logs."
    )


if __name__ == "__main__":
    main()
