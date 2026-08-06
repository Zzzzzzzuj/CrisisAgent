import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)

from backend.config import get_config
from backend.core.dynamic_runtime import run_dynamic_agent
from backend.evaluation import evaluate_agent_run
from backend.llm import LLMClient, parse_json_response, validate_required_fields


DEMO_EVENT = "某食品品牌被曝光使用过期原料，相关视频在网络传播，消费者要求监管介入"
EXPECTED_AGENTS = ["sentiment", "writer", "redteam", "legal", "writer_v2", "decision"]


def main() -> int:
    try:
        _validate_real_llm_config()
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "status": "config_error",
                    "message": str(exc),
                    "required_env": [
                        "AGENT_MODE=llm",
                        "LLM_PROVIDER=openai_compatible",
                        "LLM_MODEL",
                        "LLM_API_KEY",
                        "LLM_BASE_URL",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    try:
        llm_preflight = _run_llm_preflight()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "llm_preflight_failed",
                    "message": f"{exc.__class__.__name__}: {exc}",
                    "hint": "模型预检失败，Dynamic Runtime 若继续运行会 fallback 到 mock。请先检查 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL、账户额度和 OpenAI-compatible 协议兼容性。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    try:
        result = run_dynamic_agent(DEMO_EVENT)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "runtime_error",
                    "message": f"{exc.__class__.__name__}: {exc}",
                    "hint": "请检查模型服务地址、模型名称、API Key、网络连接和供应商 OpenAI-compatible 协议兼容性。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    results = result.get("results", {})
    decision_result = results.get("decision", {})
    final_statement = decision_result.get("final_statement", "")
    evaluation_result = evaluate_agent_run(
        event=result.get("event", DEMO_EVENT),
        results=results,
        final_statement=final_statement,
        agent_trace=result.get("execution_trace", []),
    )
    all_agents_success = _all_agents_success(result)

    print(
        json.dumps(
            {
                "status": "completed",
                "all_agents_success": all_agents_success,
                "llm_preflight": llm_preflight,
                "session_id": result.get("session_id"),
                "planner_plan": {
                    "raw_plan": result.get("raw_plan"),
                    "validated_plan": result.get("validated_plan"),
                    "executed_agents": result.get("executed_agents", []),
                    "failed_agents": result.get("failed_agents", []),
                },
                "agent_execution_trace": _summarize_trace(result.get("execution_trace", [])),
                "sentiment_result": results.get("sentiment", {}),
                "writer_draft": results.get("writer", {}),
                "redteam_review": results.get("redteam", {}),
                "legal_review": results.get("legal", {}),
                "writer_v2_result": results.get("writer_v2", {}),
                "decision_result": decision_result,
                "evaluation_result": evaluation_result,
                "note": "Dynamic Runtime 当前 trace 记录执行成功/失败；如模型调用失败但 Agent fallback 成功，请查看运行日志中的 fallback warning。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_agents_success else 2


def _validate_real_llm_config() -> None:
    os.environ["AGENT_MODE"] = "llm"
    get_config.cache_clear()
    config = get_config()
    provider = os.getenv("LLM_PROVIDER", "openai_compatible").strip() or "openai_compatible"

    if provider != "openai_compatible":
        raise ValueError(f"当前 demo 仅支持 LLM_PROVIDER=openai_compatible，实际为 {provider}。")
    if not config.llm_api_key:
        raise ValueError("缺少 LLM_API_KEY，无法运行真实 LLM demo。")
    if not config.llm_base_url:
        raise ValueError("缺少 LLM_BASE_URL，无法运行真实 LLM demo。")
    if not config.llm_model:
        raise ValueError("缺少 LLM_MODEL，无法运行真实 LLM demo。")


def _run_llm_preflight() -> dict:
    raw_response = LLMClient().chat(
        messages=[
            {
                "role": "system",
                "content": "Return JSON only.",
            },
            {
                "role": "user",
                "content": 'Return exactly {"ok": true, "message": "ready"}.',
            },
        ],
        temperature=0.0,
    )
    parsed = parse_json_response(raw_response)
    validate_required_fields(parsed, ["ok", "message"])
    return {
        "ok": bool(parsed["ok"]),
        "message": str(parsed["message"]),
    }


def _all_agents_success(result: dict) -> bool:
    executed_agents = result.get("executed_agents", [])
    failed_agents = result.get("failed_agents", [])
    trace = result.get("execution_trace", [])
    return (
        executed_agents == EXPECTED_AGENTS
        and not failed_agents
        and all(item.get("status") == "success" for item in trace)
    )


def _summarize_trace(trace: list[dict]) -> list[dict]:
    return [
        {
            "agent": item.get("agent"),
            "status": item.get("status"),
            "start_time": item.get("start_time"),
            "end_time": item.get("end_time"),
            "error": item.get("error"),
        }
        for item in trace
    ]


if __name__ == "__main__":
    raise SystemExit(main())
