import json
import subprocess
import sys
from pathlib import Path

import httpx

from evaluation.real_eval_network_guard import (
    WINDOWS_PROACTOR_SOCKETPAIR,
    WindowsProactorSocketpairCapability,
    classify_callsite_stack,
    effective_proxy_for_url,
    callsite_attribution,
    logical_destination,
    logical_destination_allowed,
    make_diagnostic,
    parse_proxy_endpoint,
    transport_allowed,
)


def test_deepseek_direct_transport_is_allowed_without_network():
    logical = logical_destination("https", "api.deepseek.com", 443)
    assert logical_destination_allowed(logical, mode="real")
    assert transport_allowed(
        logical, "api.deepseek.com", 443, mode="real", proxy_url=None,
    ) == (True, "ALLOWED")


def test_deepseek_via_explicit_loopback_proxy_is_allowed_without_network():
    logical = logical_destination("https", "api.deepseek.com", 443)
    proxy = "http://127.0.0.1:7890"
    assert parse_proxy_endpoint(proxy).host == "127.0.0.1"
    assert parse_proxy_endpoint(proxy).port == 7890
    assert transport_allowed(
        logical, "127.0.0.1", 7890, mode="real", proxy_url=proxy,
    ) == (True, "ALLOWED")


def test_explicit_localhost_proxy_aliases_are_supported_only_at_the_configured_port():
    logical = logical_destination("https", "api.deepseek.com", 443)
    for proxy in ("http://localhost:7890", "http://[::1]:7890"):
        endpoint = parse_proxy_endpoint(proxy)
        assert endpoint is not None
        assert transport_allowed(
            logical, endpoint.host, 7890, mode="real", proxy_url=proxy,
        ) == (True, "ALLOWED")


def test_disallowed_logical_hosts_remain_blocked_through_loopback_proxy():
    proxy = "http://127.0.0.1:7890"
    for host in ("example.com", "newsapi.org", "unknown.invalid"):
        logical = logical_destination("https", host, 443)
        assert not logical_destination_allowed(logical, mode="real")
        assert transport_allowed(
            logical, "127.0.0.1", 7890, mode="real", proxy_url=proxy,
        ) == (False, "LOGICAL_HOST_NOT_ALLOWED")


def test_remote_proxy_is_rejected_even_for_allowed_logical_destination():
    logical = logical_destination("https", "api.deepseek.com", 443)
    remote_proxy = "http://198.51.100.20:7890"
    assert parse_proxy_endpoint(remote_proxy) is None
    assert transport_allowed(
        logical, "198.51.100.20", 7890, mode="real", proxy_url=remote_proxy,
    ) == (False, "PROXY_NOT_ALLOWED")


def test_unconfigured_loopback_port_is_rejected():
    logical = logical_destination("https", "api.deepseek.com", 443)
    assert transport_allowed(
        logical, "127.0.0.1", 7891, mode="real",
        proxy_url="http://127.0.0.1:7890",
    ) == (False, "TRANSPORT_NOT_ALLOWED")


def test_httpx_environment_matching_honors_no_proxy_entries():
    proxies = {
        "https://": "http://127.0.0.1:7890",
        "all://": "http://127.0.0.1:7890",
        "all://*example.com": None,
    }
    assert effective_proxy_for_url("https://api.deepseek.com/v1", proxies) == "http://127.0.0.1:7890"
    assert effective_proxy_for_url("https://example.com/path", proxies) is None


def test_fake_mode_blocks_provider_socket_transport():
    fake_logical = logical_destination("http", "testserver", 80)
    assert logical_destination_allowed(fake_logical, mode="fake")
    assert transport_allowed(
        fake_logical, "127.0.0.1", 7890, mode="fake",
        proxy_url="http://127.0.0.1:7890",
    ) == (False, "TRANSPORT_NOT_ALLOWED")
    provider = logical_destination("https", "api.deepseek.com", 443)
    assert not logical_destination_allowed(provider, mode="fake")


def test_offline_eval_guard_still_blocks_provider_before_transport(monkeypatch):
    from backend.llm.offline_guard import OfflineNetworkBlockedError, assert_external_model_call_allowed

    monkeypatch.setenv("OFFLINE_EVAL", "1")
    try:
        assert_external_model_call_allowed(provider="openai_compatible", operation="chat.completions")
    except OfflineNetworkBlockedError:
        pass
    else:
        raise AssertionError("Offline Eval must remain fail-closed")


def test_network_diagnostic_is_allowlisted_and_contains_no_url_or_credentials():
    diagnostic = make_diagnostic(
        block_stage="socket_connect", destination=logical_destination("https", "api.deepseek.com", 443),
        transport_host="127.0.0.1", transport_port=7891,
        proxy_detected=True, reason_code="TRANSPORT_NOT_ALLOWED",
    )
    assert diagnostic == {
        "block_stage": "socket_connect", "logical_host": "api.deepseek.com",
        "logical_scheme": "https", "transport_host": "127.0.0.1",
        "transport_port": 7891, "proxy_detected": True,
        "reason_code": "TRANSPORT_NOT_ALLOWED",
    }
    assert "url" not in json.dumps(diagnostic).casefold()
    assert "authorization" not in json.dumps(diagnostic).casefold()


def test_callsite_attribution_is_redacted_and_limited_to_safe_frame_metadata():
    secret = "authorization-do-not-capture"

    def trigger_block():
        return callsite_attribution()

    attribution = trigger_block()
    serialized = json.dumps(attribution)
    assert attribution["caller_module"].endswith("test_real_eval_network_guard")
    assert attribution["caller_function"] == "trigger_block"
    assert attribution["caller_file_basename"] == "test_real_eval_network_guard.py"
    assert attribution["origin_module"].endswith("test_real_eval_network_guard")
    assert attribution["origin_function"] == "trigger_block"
    assert len(attribution["call_stack_frames"]) <= 12
    assert all(set(frame) == {"module", "function", "file_basename"}
               for frame in attribution["call_stack_frames"])
    assert "authorization-do-not-capture" not in serialized
    assert "C:\\Users" not in serialized
    assert secret not in serialized


def test_real_guard_rejects_non_allowlisted_http_request_without_sending(monkeypatch):
    from contextlib import ExitStack

    from scripts.run_real_llm_semantic_validation import ExternalRequestBlocked, _network_guard

    monkeypatch.setattr(
        "httpx._utils.get_environment_proxies",
        lambda: {"https://": "http://127.0.0.1:7890"},
    )
    attempts = []
    with ExitStack() as stack:
        _network_guard(stack, "real", "api.deepseek.com", attempts)
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
        try:
            try:
                client.get("https://example.com/private?token=not-recorded")
            except ExternalRequestBlocked:
                pass
            else:
                raise AssertionError("Disallowed logical host must be blocked before transport")
        finally:
            client.close()
    assert len(attempts) == 1
    assert attempts[0]["logical_host"] == "example.com"
    assert attempts[0]["proxy_detected"] is True
    assert "private" not in json.dumps(attempts)
    assert "token" not in json.dumps(attempts)


def test_real_guard_accepts_synthetic_deepseek_request_with_local_proxy(monkeypatch):
    from contextlib import ExitStack

    from scripts.run_real_llm_semantic_validation import _network_guard

    monkeypatch.setattr(
        "httpx._utils.get_environment_proxies",
        lambda: {"https://": "http://127.0.0.1:7890"},
    )
    attempts = []
    with ExitStack() as stack:
        _network_guard(stack, "real", "api.deepseek.com", attempts)
        client = httpx.Client(
            trust_env=False,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
        )
        try:
            response = client.get("https://api.deepseek.com/v1/chat/completions?ignored=yes")
        finally:
            client.close()
    assert response.status_code == 200
    assert attempts == []


def test_configured_proxy_with_credentials_is_parsed_without_exposing_them():
    endpoint = parse_proxy_endpoint("http://user:secret@127.0.0.1:7890")
    assert endpoint is not None
    assert endpoint.scheme == "http"
    assert endpoint.host == "127.0.0.1"
    assert endpoint.port == 7890
    assert "user" not in repr(endpoint)
    assert "secret" not in repr(endpoint)


def test_windows_socketpair_capability_requires_runtime_callsite_and_loopback(monkeypatch):
    import evaluation.real_eval_network_guard as guard

    monkeypatch.setattr(guard.sys, "platform", "win32")
    capability = WindowsProactorSocketpairCapability(enabled=True)
    valid_attribution = {
        "call_stack_category": WINDOWS_PROACTOR_SOCKETPAIR,
        "caller_module": "socket",
        "caller_function": "socketpair",
        "caller_file_basename": "socket.py",
        "call_stack_frames": [
            {"module": "socket", "function": "socketpair", "file_basename": "socket.py"},
            {"module": "asyncio.proactor_events", "function": "_make_self_pipe",
             "file_basename": "proactor_events.py"},
            {"module": "asyncio.proactor_events", "function": "__init__",
             "file_basename": "proactor_events.py"},
        ],
    }
    ordinary_attribution = {
        "call_stack_category": "application_or_unknown",
        "caller_module": "tests.test_real_eval_network_guard",
        "caller_function": "test_app_socket",
        "caller_file_basename": "test_real_eval_network_guard.py",
        "call_stack_frames": [],
    }
    forged_category_only = {
        "call_stack_category": WINDOWS_PROACTOR_SOCKETPAIR,
        "call_stack_frames": [
            {"module": "socket", "function": "socketpair", "file_basename": "socket.py"},
        ],
    }

    with capability.portal_bootstrap_window():
        assert capability._authorize(
            host="127.0.0.1", provider_context_present=False,
            attribution=ordinary_attribution,
        ) == (False, "TRANSPORT_NOT_ALLOWED")
        assert capability._authorize(
            host="127.0.0.1", provider_context_present=True,
            attribution=valid_attribution,
        ) == (False, "TRANSPORT_NOT_ALLOWED")
        assert capability._authorize(
            host="127.0.0.1", provider_context_present=False,
            attribution=forged_category_only,
        ) == (False, "TRANSPORT_NOT_ALLOWED")
        assert capability._authorize(
            host="example.com", provider_context_present=False,
            attribution=valid_attribution,
        ) == (False, "TRANSPORT_NOT_ALLOWED")
        assert capability._authorize(
            host="127.0.0.1", provider_context_present=False,
            attribution=valid_attribution,
        ) == (True, "ALLOWED")
        assert capability._authorize(
            host="127.0.0.1", provider_context_present=False,
            attribution=valid_attribution,
        ) == (False, "CAPABILITY_BUDGET_EXHAUSTED")

    assert capability._authorize(
        host="127.0.0.1", provider_context_present=False,
        attribution=valid_attribution,
    ) == (False, "CAPABILITY_NOT_ACTIVE")
    assert capability.events == [{
        "capability": WINDOWS_PROACTOR_SOCKETPAIR,
        "stage": "testclient_portal_bootstrap",
        "caller_category": WINDOWS_PROACTOR_SOCKETPAIR,
        "transport_loopback": True,
        "budget_before": 1,
        "budget_after": 0,
    }]


def test_callsite_classifier_requires_full_proactor_self_pipe_origin():
    socketpair = {"module": "socket", "function": "socketpair", "file_basename": "socket.py"}
    make_pipe = {
        "module": "asyncio.proactor_events", "function": "_make_self_pipe",
        "file_basename": "proactor_events.py",
    }
    proactor_init = {
        "module": "asyncio.proactor_events", "function": "__init__",
        "file_basename": "proactor_events.py",
    }
    full_stack = [socketpair, make_pipe, proactor_init]

    assert classify_callsite_stack(full_stack, platform="win32") == WINDOWS_PROACTOR_SOCKETPAIR
    assert classify_callsite_stack([socketpair], platform="win32") != WINDOWS_PROACTOR_SOCKETPAIR
    assert classify_callsite_stack([make_pipe, proactor_init], platform="win32") != WINDOWS_PROACTOR_SOCKETPAIR
    assert classify_callsite_stack(full_stack, platform="linux") != WINDOWS_PROACTOR_SOCKETPAIR


def test_direct_cli_main_wrapper_authorizes_only_matching_origin_stack():
    import os

    if sys.platform != "win32":
        import pytest
        pytest.skip("Windows Proactor bootstrap capability is Windows-specific")

    repo_root = Path(__file__).resolve().parents[2]
    child = r'''
import json
from evaluation.real_eval_network_guard import WindowsProactorSocketpairCapability, callsite_attribution

capability = WindowsProactorSocketpairCapability(enabled=True)
with capability.portal_bootstrap_window():
    main_ns = {"__name__": "__main__", "capability": capability,
               "callsite_attribution": callsite_attribution}
    exec(compile("""
def block():
    attribution = callsite_attribution()
    allowed, reason = capability._authorize(
        host="127.0.0.1", provider_context_present=False, attribution=attribution)
    return attribution, allowed, reason
""", "run_real_llm_semantic_validation.py", "exec"), main_ns)

    socket_ns = {"__name__": "socket"}
    proactor_ns = {"__name__": "asyncio.proactor_events", "main": main_ns}
    exec(compile("""
def socketpair():
    return proactor["_make_self_pipe"]()
""", "socket.py", "exec"), socket_ns)
    exec(compile("""
def _make_self_pipe():
    return __init__()
def __init__():
    return main["block"]()
""", "proactor_events.py", "exec"), proactor_ns)
    socket_ns["proactor"] = proactor_ns

    ordinary, ordinary_allowed, ordinary_reason = main_ns["block"]()
    origin, origin_allowed, origin_reason = socket_ns["socketpair"]()
    print(json.dumps({
        "ordinary_allowed": ordinary_allowed,
        "ordinary_reason": ordinary_reason,
        "wrapper_module": origin["caller_module"],
        "wrapper_function": origin["caller_function"],
        "origin_category": origin["call_stack_category"],
        "origin_frames": origin["call_stack_frames"],
        "origin_allowed": origin_allowed,
        "origin_reason": origin_reason,
        "events": capability.events,
    }))
'''
    result = subprocess.run(
        [sys.executable, "-c", child], cwd=repo_root, text=True,
        capture_output=True, check=False, env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ordinary_allowed"] is False
    assert report["ordinary_reason"] == "TRANSPORT_NOT_ALLOWED"
    assert report["wrapper_module"] == "__main__"
    assert report["wrapper_function"] == "block"
    assert report["origin_category"] == WINDOWS_PROACTOR_SOCKETPAIR
    assert any(frame["module"] == "socket" and frame["function"] == "socketpair"
               for frame in report["origin_frames"])
    assert any(frame["module"] == "asyncio.proactor_events"
               and frame["function"] == "_make_self_pipe"
               for frame in report["origin_frames"])
    assert report["origin_allowed"] is True
    assert report["origin_reason"] == "ALLOWED"
    assert len(report["events"]) == 1


def test_unscoped_application_loopback_connection_remains_blocked(monkeypatch):
    import socket
    from contextlib import ExitStack, nullcontext

    import evaluation.real_eval_network_guard as guard
    from scripts.run_real_llm_semantic_validation import ExternalRequestBlocked, _network_guard

    monkeypatch.setattr(guard.sys, "platform", "win32")
    attempts = []
    with ExitStack() as stack:
        capability = _network_guard(stack, "real", "api.deepseek.com", attempts)
        sock = socket.socket()
        try:
            for window in (capability.portal_bootstrap_window(), nullcontext()):
                try:
                    with window:
                        sock.connect(("127.0.0.1", 49327))
                except ExternalRequestBlocked:
                    pass
                else:
                    raise AssertionError("An ordinary loopback connect must remain blocked")
        finally:
            sock.close()
    assert len(attempts) == 2
    assert all(item["reason_code"] == "TRANSPORT_NOT_ALLOWED" for item in attempts)
    assert all(item["logical_host"] is None for item in attempts)
    assert all(item["transport_host"] == "127.0.0.1" for item in attempts)
    assert all(item["caller_function"] == "block" for item in attempts)
    assert all(item["origin_module"].endswith("test_real_eval_network_guard") for item in attempts)


def test_windows_testclient_runtime_socketpair_capability_allows_only_portal_bootstrap(monkeypatch):
    import sys
    from contextlib import ExitStack

    import pytest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    if sys.platform != "win32":
        pytest.skip("Windows Proactor bootstrap capability is Windows-specific")

    from scripts.run_real_llm_semantic_validation import (
        _CapabilityScopedClient,
        ExternalRequestBlocked,
        _network_guard,
    )

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    monkeypatch.setattr(
        "httpx._utils.get_environment_proxies",
        lambda: {"https://": "http://127.0.0.1:7890"},
    )
    attempts = []
    with ExitStack() as stack:
        capability = _network_guard(stack, "real", "api.deepseek.com", attempts)
        client = TestClient(app)
        try:
            response = _CapabilityScopedClient(client, capability).get("/health")
        finally:
            client.close()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert attempts == []
    assert capability.events == [{
        "capability": WINDOWS_PROACTOR_SOCKETPAIR,
        "stage": "testclient_portal_bootstrap",
        "caller_category": WINDOWS_PROACTOR_SOCKETPAIR,
        "transport_loopback": True,
        "budget_before": 1,
        "budget_after": 0,
    }]


def test_windows_internal_capability_does_not_change_provider_proxy_policy(monkeypatch):
    import sys
    from contextlib import ExitStack

    import pytest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    if sys.platform != "win32":
        pytest.skip("Windows Proactor bootstrap capability is Windows-specific")

    from scripts.run_real_llm_semantic_validation import (
        _CapabilityScopedClient,
        ExternalRequestBlocked,
        _network_guard,
    )

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    monkeypatch.setattr(
        "httpx._utils.get_environment_proxies",
        lambda: {"https://": "http://127.0.0.1:7890"},
    )
    attempts = []
    with ExitStack() as stack:
        capability = _network_guard(stack, "real", "api.deepseek.com", attempts)
        client = TestClient(app)
        try:
            response = _CapabilityScopedClient(client, capability).get("/health")
        finally:
            client.close()

        provider = httpx.Client(
            trust_env=False,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
        )
        try:
            provider_response = provider.get("https://api.deepseek.com/v1/chat/completions")
            for host in ("example.com", "unknown.invalid"):
                try:
                    provider.get(f"https://{host}/private")
                except ExternalRequestBlocked:
                    pass
                else:
                    raise AssertionError("The loopback capability must not authorize another logical host")
        finally:
            provider.close()

    assert response.status_code == 200
    assert provider_response.status_code == 200
    assert len(attempts) == 2
    assert [item["logical_host"] for item in attempts] == ["example.com", "unknown.invalid"]
    assert all(item["proxy_detected"] is True for item in attempts)
    assert capability.events[0]["capability"] == WINDOWS_PROACTOR_SOCKETPAIR
