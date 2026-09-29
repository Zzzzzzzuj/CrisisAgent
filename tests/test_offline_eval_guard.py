import asyncio

import httpx
import pytest

from backend.config import get_config
from backend.llm.config import LLMConfig, get_llm_config
from backend.llm.client import LLMClient
from backend.llm.offline_guard import (
    OfflineNetworkBlockedError,
    assert_external_model_call_allowed,
    assert_offline_eval_startup,
)
from backend.main import app


def _reset_config_caches():
    get_config.cache_clear()
    get_llm_config.cache_clear()


def _request_dynamic_run():
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/dynamic/run",
                json={"event": "产品质量与消费者投诉事件"},
            )

    return asyncio.run(send_request())


def test_project_env_precedence_is_shell_then_backend_then_root(monkeypatch, tmp_path):
    from backend.env import load_project_env

    root = tmp_path / "project"
    backend_dir = root / "backend"
    backend_dir.mkdir(parents=True)
    (root / ".env").write_text("AGENT_MODE=root\nROOT_ONLY=yes\n", encoding="utf-8")
    (backend_dir / ".env").write_text(
        "AGENT_MODE=backend\nBACKEND_ONLY=yes\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_MODE", raising=False)
    monkeypatch.delenv("ROOT_ONLY", raising=False)
    monkeypatch.delenv("BACKEND_ONLY", raising=False)

    load_project_env(root, backend_dir)

    assert __import__("os").environ["AGENT_MODE"] == "backend"
    assert __import__("os").environ["ROOT_ONLY"] == "yes"
    assert __import__("os").environ["BACKEND_ONLY"] == "yes"

    monkeypatch.setenv("AGENT_MODE", "mock")
    load_project_env(root, backend_dir)
    assert __import__("os").environ["AGENT_MODE"] == "mock"


def test_offline_eval_startup_reports_redacted_mock_config(monkeypatch):
    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("LLM_API_KEY", "offline-test-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "offline-test-model")
    _reset_config_caches()
    try:
        summary = assert_offline_eval_startup()
    finally:
        _reset_config_caches()

    assert summary == {
        "agent_mode": "mock",
        "offline_eval": True,
        "model_provider": "openai_compatible",
        "network_policy": "external_model_http_blocked",
        "external_llm_allowed": False,
    }
    assert "offline-test-secret" not in repr(summary)


def test_dynamic_run_mock_mode_makes_zero_sync_http_requests(monkeypatch):
    calls = []

    def forbidden_http_client(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("unexpected outbound HTTP client construction")

    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("LLM_API_KEY", "offline-test-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "offline-test-model")
    monkeypatch.setattr(httpx, "Client", forbidden_http_client)
    monkeypatch.setattr("backend.main.save_checkpoint", lambda state: state.to_dict())
    _reset_config_caches()
    try:
        response = _request_dynamic_run()
    finally:
        _reset_config_caches()

    assert response.status_code == 200
    assert response.json()["status"] in {"completed", "waiting_human"}
    assert calls == []


def test_dynamic_run_rejects_llm_mode_before_running_case(monkeypatch):
    run_calls = []
    http_calls = []

    def unexpected_run(*args, **kwargs):
        run_calls.append((args, kwargs))
        raise AssertionError("case execution must not start")

    def forbidden_http_client(*args, **kwargs):
        http_calls.append((args, kwargs))
        raise AssertionError("no outbound HTTP is allowed")

    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "offline-test-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "offline-test-model")
    monkeypatch.setattr("backend.main.run_dynamic_agent", unexpected_run)
    monkeypatch.setattr(httpx, "Client", forbidden_http_client)
    _reset_config_caches()
    try:
        response = _request_dynamic_run()
    finally:
        _reset_config_caches()

    assert response.status_code == 503
    assert "AGENT_MODE=mock" in response.json()["detail"]
    assert run_calls == []
    assert http_calls == []


def test_llm_client_blocks_configured_provider_before_http(monkeypatch):
    calls = []

    def forbidden_http_client(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setattr(httpx, "Client", forbidden_http_client)
    client = LLMClient(
        config=LLMConfig(
            provider="openai_compatible",
            model="test-model",
            api_key="offline-test-secret",
            base_url="https://provider.invalid/v1",
        )
    )

    with pytest.raises(OfflineNetworkBlockedError) as error:
        client.chat([{"role": "user", "content": "offline test"}])

    assert calls == []
    assert "offline-test-secret" not in str(error.value)
    assert "Authorization" not in str(error.value)


def test_legacy_llm_client_is_blocked_before_http(monkeypatch):
    calls = []

    def forbidden_http_client(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setenv("OFFLINE_EVAL", "1")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "offline-test-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "offline-test-model")
    monkeypatch.setattr(httpx, "Client", forbidden_http_client)
    _reset_config_caches()
    try:
        from backend.llm_client import call_llm

        with pytest.raises(OfflineNetworkBlockedError):
            call_llm("offline test")
    finally:
        _reset_config_caches()

    assert calls == []


def test_external_model_calls_are_allowed_by_guard_outside_offline_eval(monkeypatch):
    monkeypatch.delenv("OFFLINE_EVAL", raising=False)
    assert_external_model_call_allowed(
        provider="openai_compatible",
        operation="chat.completions",
    )
