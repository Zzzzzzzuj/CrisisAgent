"""Network policy helpers for the explicitly authorized Real Eval runner.

This module is intentionally separate from the production LLM client. It
allows one logical provider destination and, when configured, one validated
loopback proxy transport for that request.
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit


ALLOWED_PROVIDER_SCHEME = "https"
ALLOWED_PROVIDER_HOST = "api.deepseek.com"
ALLOWED_PROVIDER_PORT = 443
_LOOPBACK_NAMES = {"localhost"}
_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9_.:\-\[\]]{1,200}$")
_SAFE_FRAME_RE = re.compile(r"^[A-Za-z0-9_.<>:-]{1,160}$")
_INSTRUMENTATION_MODULES = {
    "evaluation.real_eval_network_guard",
    "scripts.run_real_llm_semantic_validation",
}
_RUNNER_WRAPPER_FUNCTIONS = {
    "block", "request_context", "sync_send", "async_send", "guarded_getaddrinfo",
    "check_socket_transport", "guarded_connect", "guarded_connect_ex", "_authorize",
}
WINDOWS_PROACTOR_SOCKETPAIR = "WINDOWS_PROACTOR_SOCKETPAIR"
_TESTCLIENT_PORTAL_BOOTSTRAP = "testclient_portal_bootstrap"
_PROACTOR_SOCKETPAIR_BUDGET = 1


@dataclass(frozen=True)
class ProxyEndpoint:
    scheme: str
    host: str
    port: int


@dataclass(frozen=True)
class LogicalDestination:
    scheme: str
    host: str
    port: int


class WindowsProactorSocketpairCapability:
    """Permit only one verified Proactor self-pipe connect per TestClient portal startup."""

    def __init__(self, *, enabled: bool):
        self._enabled = enabled and sys.platform == "win32"
        self._lock = threading.Lock()
        self._window: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events]

    @contextmanager
    def portal_bootstrap_window(self) -> Iterator[None]:
        """Scope capability to one synchronous TestClient call that starts a portal."""
        if not self._enabled:
            yield
            return
        with self._lock:
            if self._window is not None:
                raise RuntimeError("Nested TestClient portal capability windows are not allowed")
            self._window = {
                "stage": _TESTCLIENT_PORTAL_BOOTSTRAP,
                "active": True,
                "budget": _PROACTOR_SOCKETPAIR_BUDGET,
                "remaining": _PROACTOR_SOCKETPAIR_BUDGET,
            }
        try:
            yield
        finally:
            with self._lock:
                self._window = None

    def _authorize(self, *, host: Any, provider_context_present: bool,
                   attribution: Mapping[str, Any]) -> tuple[bool, str]:
        """Consume the narrow capability only for the verified runtime self-pipe callsite."""
        with self._lock:
            window = self._window
            if not self._enabled or window is None:
                return False, "CAPABILITY_NOT_ACTIVE"
            if window["remaining"] <= 0:
                return False, "CAPABILITY_BUDGET_EXHAUSTED"
            if (not window["active"] or window["stage"] != _TESTCLIENT_PORTAL_BOOTSTRAP
                    or provider_context_present or not _is_loopback_name(str(host))
                    or not _is_windows_proactor_socketpair_attribution(attribution)):
                return False, "TRANSPORT_NOT_ALLOWED"

            before = window["remaining"]
            window["remaining"] -= 1
            window["active"] = False
            self._events.append({
                "capability": WINDOWS_PROACTOR_SOCKETPAIR,
                "stage": window["stage"],
                "caller_category": WINDOWS_PROACTOR_SOCKETPAIR,
                "transport_loopback": True,
                "budget_before": before,
                "budget_after": window["remaining"],
            })
            return True, "ALLOWED"


def _is_windows_proactor_socketpair_attribution(attribution: Mapping[str, Any]) -> bool:
    frames = attribution.get("call_stack_frames")
    return isinstance(frames, list) and classify_callsite_stack(frames) == WINDOWS_PROACTOR_SOCKETPAIR


def classify_callsite_stack(
    frames: list[Mapping[str, Any]], *, platform: str | None = None,
) -> str:
    """Classify one bounded, redacted origin stack for both diagnostics and authorization."""
    current_platform = platform or sys.platform
    frame_keys = {
        (item.get("module"), item.get("function"), item.get("file_basename"))
        for item in frames if isinstance(item, Mapping)
    }
    has_socketpair = ("socket", "socketpair", "socket.py") in frame_keys
    has_proactor_self_pipe = (
        ("asyncio.proactor_events", "_make_self_pipe", "proactor_events.py") in frame_keys
        and ("asyncio.proactor_events", "__init__", "proactor_events.py") in frame_keys
    )
    if current_platform == "win32" and has_socketpair and has_proactor_self_pipe:
        return WINDOWS_PROACTOR_SOCKETPAIR

    modules = [str(item.get("module", "")) for item in frames if isinstance(item, Mapping)]
    prefixes = (
        ("test_client", ("starlette.testclient", "fastapi.testclient")),
        ("http_client", ("httpx", "requests")),
        ("redis", ("redis", "rq")),
        ("database", ("sqlalchemy", "psycopg", "asyncpg")),
        ("server", ("uvicorn",)),
        ("async_runtime", ("asyncio", "anyio", "trio")),
        ("process", ("subprocess", "multiprocessing")),
    )
    for label, candidates in prefixes:
        if any(module == prefix or module.startswith(prefix + ".")
               for module in modules for prefix in candidates):
            return label
    return "application_or_unknown"


def safe_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if _SAFE_HOST_RE.fullmatch(candidate) else None


def _is_loopback_name(host: str) -> bool:
    normalized = host.strip("[]").casefold()
    if normalized in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def parse_proxy_endpoint(proxy_url: str | None) -> ProxyEndpoint | None:
    """Parse a proxy URL without retaining or returning its credentials."""
    if not proxy_url:
        return None
    try:
        parsed = urlsplit(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
        host = (parsed.hostname or "").casefold()
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme not in {"http", "https"} or not host or port is None:
        return None
    if not _is_loopback_name(host) or not 1 <= port <= 65535:
        return None
    return ProxyEndpoint(parsed.scheme, host, port)


def effective_proxy_for_url(url: Any, proxy_map: Mapping[str, str | None] | None = None) -> str | None:
    """Resolve the same environment proxy mapping that HTTPX uses."""
    import httpx
    from httpx._utils import URLPattern, get_environment_proxies

    mappings = get_environment_proxies() if proxy_map is None else proxy_map
    patterns = [(URLPattern(pattern), proxy) for pattern, proxy in mappings.items()]
    target = url if isinstance(url, httpx.URL) else httpx.URL(str(url))
    for pattern, proxy in sorted(patterns, key=lambda item: item[0]):
        if pattern.matches(target):
            return proxy
    return None


def logical_destination(scheme: str, host: str, port: int | None = None) -> LogicalDestination:
    normalized_scheme = (scheme or "").casefold()
    normalized_host = (host or "").casefold().rstrip(".")
    effective_port = port or (443 if normalized_scheme == "https" else 80)
    return LogicalDestination(normalized_scheme, normalized_host, effective_port)


def logical_destination_allowed(destination: LogicalDestination, *, mode: str) -> bool:
    if mode == "fake":
        return destination.host == "testserver"
    return (
        mode == "real"
        and destination.scheme == ALLOWED_PROVIDER_SCHEME
        and destination.host == ALLOWED_PROVIDER_HOST
        and destination.port == ALLOWED_PROVIDER_PORT
    )


def transport_allowed(
    destination: LogicalDestination,
    transport_host: str,
    transport_port: int | None,
    *,
    mode: str,
    proxy_url: str | None,
    resolved_transport_hosts: set[str] | None = None,
) -> tuple[bool, str]:
    """Check the TCP target, binding it to an already-allowed logical URL."""
    if not logical_destination_allowed(destination, mode=mode):
        return False, "LOGICAL_HOST_NOT_ALLOWED"
    if mode != "real":
        return False, "TRANSPORT_NOT_ALLOWED"

    if proxy_url is not None:
        endpoint = parse_proxy_endpoint(proxy_url)
        if endpoint is None:
            return False, "PROXY_NOT_ALLOWED"
        allowed_hosts = {endpoint.host}
        if resolved_transport_hosts:
            allowed_hosts.update(item.casefold() for item in resolved_transport_hosts)
        host = (transport_host or "").casefold().strip("[]")
        if host not in {item.strip("[]") for item in allowed_hosts} or transport_port != endpoint.port:
            return False, "TRANSPORT_NOT_ALLOWED"
        try:
            if ipaddress.ip_address(host).is_loopback is False:
                return False, "TRANSPORT_NOT_ALLOWED"
        except ValueError:
            if host != "localhost":
                return False, "TRANSPORT_NOT_ALLOWED"
        return True, "ALLOWED"

    if transport_port != ALLOWED_PROVIDER_PORT:
        return False, "TRANSPORT_NOT_ALLOWED"
    host = (transport_host or "").casefold().strip("[]")
    allowed_hosts = {ALLOWED_PROVIDER_HOST}
    if resolved_transport_hosts:
        allowed_hosts.update(item.casefold().strip("[]") for item in resolved_transport_hosts)
    return (host in allowed_hosts, "ALLOWED" if host in allowed_hosts else "TRANSPORT_NOT_ALLOWED")


def normalize_port(value: Any) -> int | None:
    if isinstance(value, int):
        return value if 0 < value <= 65535 else None
    if isinstance(value, str):
        value = value.strip().casefold()
        if value == "https":
            return 443
        if value == "http":
            return 80
        if value.isdigit():
            port = int(value)
            return port if 0 < port <= 65535 else None
    return None


def make_diagnostic(
    *, block_stage: str,
    destination: LogicalDestination | None,
    transport_host: Any = None,
    transport_port: Any = None,
    proxy_detected: bool = False,
    reason_code: str,
) -> dict[str, Any]:
    """Return only allowlisted network metadata; never URL/query/body/credentials."""
    return {
        "block_stage": block_stage[:40],
        "logical_host": safe_host(destination.host) if destination else None,
        "logical_scheme": destination.scheme[:12] if destination else None,
        "transport_host": safe_host(str(transport_host)) if transport_host is not None else None,
        "transport_port": normalize_port(transport_port),
        "proxy_detected": bool(proxy_detected),
        "reason_code": reason_code[:40],
    }


def callsite_attribution(max_frames: int = 12) -> dict[str, Any]:
    """Separate the immediate guard wrapper from a short, sanitized origin stack."""
    raw_frames: list[dict[str, str]] = []
    origin_frames: list[dict[str, str]] = []
    frame = sys._getframe(1)
    while frame is not None and len(raw_frames) < 24:
        module = str(frame.f_globals.get("__name__", "unknown"))
        raw_function = frame.f_code.co_name
        raw_file = os.path.basename(frame.f_code.co_filename)
        safe_module = module if _SAFE_FRAME_RE.fullmatch(module) else "unknown"
        safe_function = raw_function if _SAFE_FRAME_RE.fullmatch(raw_function) else "unknown"
        safe_file = raw_file if _SAFE_FRAME_RE.fullmatch(raw_file) else "unknown"
        item = {"module": safe_module, "function": safe_function, "file_basename": safe_file}
        raw_frames.append(item)
        is_runner_wrapper = (
            module == "__main__" and raw_file == "run_real_llm_semantic_validation.py"
            and raw_function in _RUNNER_WRAPPER_FUNCTIONS
        )
        if module not in _INSTRUMENTATION_MODULES and not is_runner_wrapper:
            origin_frames.append(item)
        frame = frame.f_back

    caller = raw_frames[0] if raw_frames else {"module": "unknown", "function": "unknown", "file_basename": "unknown"}
    origin = origin_frames[0] if origin_frames else {"module": "unknown", "function": "unknown", "file_basename": "unknown"}
    bounded_origin = origin_frames[:max(0, min(max_frames, 12))]
    return {
        "caller_module": caller["module"],
        "caller_function": caller["function"],
        "caller_file_basename": caller["file_basename"],
        "origin_module": origin["module"],
        "origin_function": origin["function"],
        "origin_file_basename": origin["file_basename"],
        "call_stack_category": classify_callsite_stack(bounded_origin),
        "call_stack_frames": bounded_origin,
    }
