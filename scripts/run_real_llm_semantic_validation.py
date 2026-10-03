"""Reusable five-case Dynamic Runtime evaluation runner.

Default mode is strictly fake/offline. Real mode is opt-in and restricted to
the configured DeepSeek API host; this script is never run against real mode by
the repository test suite.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import sys
import tempfile
from contextvars import ContextVar
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

# Direct script execution puts ``scripts/`` rather than the repository root on
# sys.path. Bootstrap the root before importing repository packages.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.real_eval_network_guard import (
    WindowsProactorSocketpairCapability,
    effective_proxy_for_url,
    callsite_attribution,
    logical_destination,
    logical_destination_allowed,
    make_diagnostic,
    normalize_port,
    parse_proxy_endpoint,
    transport_allowed,
)
from backend.env import load_project_env

FROZEN_CASE_PATH = ROOT / "evaluation" / "dynamic_real_case_v1.json"
EXPECTED_FROZEN_SHA256 = "8d5b0f979350db7f0d1ba2bbd23f1dd308d5f618f5333a2b73b336ce29d4aa40"
DEFAULT_CASE_IDS = ("privacy-03", "food-03", "outage-01", "complaint-02", "outage-02")
DEFAULT_REPORT_DIR = ROOT / "evaluation" / "reports"

class ExternalRequestBlocked(RuntimeError):
    def __init__(self, diagnostic: Mapping[str, Any]):
        super().__init__("Evaluation runner blocked a network request by policy.")
        self.diagnostic = dict(diagnostic)


class _CapabilityScopedClient:
    """Wrap each TestClient call in the matching temporary portal-bootstrap window."""

    def __init__(self, client, socket_capability):
        self._client = client
        self._socket_capability = socket_capability

    def _request(self, method, *args, **kwargs):
        window = (self._socket_capability.portal_bootstrap_window()
                  if self._socket_capability is not None else nullcontext())
        with window:
            return getattr(self._client, method)(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._request("get", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._request("post", *args, **kwargs)


def load_frozen_cases(path: Path | None = None) -> tuple[list[dict[str, Any]], str]:
    path = path or FROZEN_CASE_PATH
    raw = path.read_bytes()
    actual_hash = _frozen_identity_sha256(raw)
    if actual_hash != EXPECTED_FROZEN_SHA256:
        raise RuntimeError(
            f"Frozen case SHA-256 mismatch: expected {EXPECTED_FROZEN_SHA256}, got {actual_hash}; stopped."
        )
    document = json.loads(raw.decode("utf-8"))
    by_id = {case.get("case_id"): case for case in document.get("cases", [])}
    missing = [case_id for case_id in DEFAULT_CASE_IDS if case_id not in by_id]
    if missing:
        raise RuntimeError(f"Frozen case slice is incomplete: {', '.join(missing)}")
    return [by_id[case_id] for case_id in DEFAULT_CASE_IDS], actual_hash


def _frozen_identity_sha256(raw: bytes) -> str:
    """Hash frozen text independent of platform newline conversion only."""
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _fake_environment(temp_root: Path) -> dict[str, str]:
    values = {
        "AGENT_MODE": "mock", "OFFLINE_EVAL": "1", "AUTH_ENABLED": "false",
        "RUNTIME_MODE": "sync", "TASK_QUEUE_BACKEND": "inprocess",
        "CHECKPOINT_STORAGE": "json",
        "DATABASE_URL": f"sqlite:///{(temp_root / 'unused.sqlite').as_posix()}",
        "VECTOR_BACKEND": "json", "EMBEDDING_MODEL": "hash", "RAG_ENABLED": "true",
        "LLM_PROVIDER": "openai_compatible", "LLM_API_KEY": "offline-runner-placeholder",
        "LLM_BASE_URL": "mock://blocked", "LLM_MODEL": "offline-evaluation-only",
    }
    store_names = (
        "HARNESS_SPEC_STORE_PATH", "CASE_MEMORY_STORE_PATH", "AUDIT_LOG_STORE_PATH",
        "SOURCE_REGISTRY_RUNTIME_PATH", "INGESTION_RUN_STORE_PATH", "CRISIS_EVENT_STORE_PATH",
        "EVENT_AGENT_RUN_STORE_PATH", "EVAL_RUN_STORE_PATH", "ALERT_STORE_PATH",
        "COLLECTED_ITEM_STORE_PATH", "WATCHLIST_STORE_PATH", "HARNESS_COMPARISON_STORE_PATH",
        "HARNESS_PROPOSAL_STORE_PATH",
    )
    values.update({name: str(temp_root / f"{name.lower()}.json") for name in store_names})
    return values


def _network_guard(stack: ExitStack, mode: str, allowed_provider_host: str | None,
                   attempts: list[dict[str, Any]], diagnostic_sink=None
                   ) -> WindowsProactorSocketpairCapability:
    import httpx

    class RequestContext:
        def __init__(self, destination, proxy_url, proxy_detected):
            self.destination = destination
            self.proxy_url = proxy_url
            self.proxy_detected = proxy_detected
            self.resolved_transport_hosts: set[str] = set()

    active_request: ContextVar[RequestContext | None] = ContextVar(
        f"real_eval_network_context_{id(attempts)}", default=None
    )
    internal_socket_capability = WindowsProactorSocketpairCapability(enabled=mode == "real")

    def block(stage: str, destination, transport_host=None, transport_port=None,
              proxy_detected=False, reason="TRANSPORT_NOT_ALLOWED"):
        diagnostic = make_diagnostic(
            block_stage=stage, destination=destination,
            transport_host=transport_host, transport_port=transport_port,
            proxy_detected=proxy_detected, reason_code=reason,
        )
        diagnostic.update(callsite_attribution())
        attempts.append(diagnostic)
        if diagnostic_sink is not None:
            diagnostic_sink(diagnostic)
        raise ExternalRequestBlocked(diagnostic)

    def request_context(request):
        url = request.url
        destination = logical_destination(url.scheme, url.host, url.port)
        proxy_url = effective_proxy_for_url(url) if mode == "real" else None
        proxy_detected = proxy_url is not None
        if not logical_destination_allowed(destination, mode=mode):
            block("http_request", destination, proxy_detected=proxy_detected,
                  reason="LOGICAL_HOST_NOT_ALLOWED")
        if proxy_url is not None and parse_proxy_endpoint(proxy_url) is None:
            parsed = httpx.URL(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
            block("proxy_config", destination, parsed.host, parsed.port,
                  proxy_detected=True, reason="PROXY_NOT_ALLOWED")
        return RequestContext(destination, proxy_url, proxy_detected)

    original_sync_send = httpx.Client.send
    original_async_send = httpx.AsyncClient.send

    def sync_send(client, request, *args, **kwargs):
        context = request_context(request)
        token = active_request.set(context)
        try:
            return original_sync_send(client, request, *args, **kwargs)
        finally:
            active_request.reset(token)

    async def async_send(client, request, *args, **kwargs):
        context = request_context(request)
        token = active_request.set(context)
        try:
            return await original_async_send(client, request, *args, **kwargs)
        finally:
            active_request.reset(token)

    stack.enter_context(patch.object(httpx.Client, "send", sync_send))
    stack.enter_context(patch.object(httpx.AsyncClient, "send", async_send))

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def configured_loopback_proxy_endpoints() -> set[tuple[str, int]]:
        from httpx._utils import get_environment_proxies

        result = set()
        for proxy_value in get_environment_proxies().values():
            endpoint = parse_proxy_endpoint(proxy_value)
            if endpoint is not None:
                result.add((endpoint.host.strip("[]"), endpoint.port))
        return result

    fake_proxy_endpoints = configured_loopback_proxy_endpoints()

    def is_fake_internal_socket(host: Any, port: Any) -> bool:
        try:
            normalized_host = str(host).casefold().strip("[]")
            normalized_port = normalize_port(port)
            try:
                is_loopback = ipaddress.ip_address(normalized_host).is_loopback
            except ValueError:
                is_loopback = normalized_host == "localhost"
            return bool(
                is_loopback and normalized_port is not None and normalized_port >= 32768
                and (normalized_host, normalized_port) not in fake_proxy_endpoints
            )
        except (TypeError, ValueError):
            return False

    def address_parts(address: Any) -> tuple[Any, Any]:
        if isinstance(address, tuple) and address:
            return address[0], address[1] if len(address) > 1 else None
        return address, None

    def guarded_getaddrinfo(host, port=0, *args, **kwargs):
        context = active_request.get()
        destination = context.destination if context else None
        proxy_detected = context.proxy_detected if context else False
        requested_port = normalize_port(port)
        if context is None:
            if mode == "fake" and is_fake_internal_socket(host, requested_port):
                results = original_getaddrinfo(host, port, *args, **kwargs)
                if all(item[4] and ipaddress.ip_address(item[4][0]).is_loopback for item in results):
                    return results
            block("dns", None, host, requested_port, reason="TRANSPORT_NOT_ALLOWED")

        if context.proxy_url is not None:
            endpoint = parse_proxy_endpoint(context.proxy_url)
            assert endpoint is not None
            candidate = str(host).casefold().strip("[]")
            configured = endpoint.host.casefold().strip("[]")
            alias_ok = configured == "localhost" and candidate in {"127.0.0.1", "::1"}
            if candidate != configured and not alias_ok:
                block("dns", destination, host, requested_port, proxy_detected,
                      "TRANSPORT_NOT_ALLOWED")
            if requested_port is not None and requested_port != endpoint.port:
                block("dns", destination, host, requested_port, proxy_detected,
                      "TRANSPORT_NOT_ALLOWED")
            results = original_getaddrinfo(host, port, *args, **kwargs)
            for item in results:
                resolved_host = item[4][0] if item[4] else ""
                try:
                    is_loopback = ipaddress.ip_address(resolved_host).is_loopback
                except ValueError:
                    is_loopback = False
                if not is_loopback:
                    block("dns", destination, resolved_host, endpoint.port,
                          proxy_detected, "TRANSPORT_NOT_ALLOWED")
                context.resolved_transport_hosts.add(resolved_host.casefold())
            return results

        if (mode != "real" or destination.host != allowed_provider_host
                or str(host).casefold().rstrip(".") != allowed_provider_host
                or requested_port not in {None, 443}):
            block("dns", destination, host, requested_port, proxy_detected,
                  "TRANSPORT_NOT_ALLOWED")
        results = original_getaddrinfo(host, port, *args, **kwargs)
        context.resolved_transport_hosts.update(
            item[4][0].casefold() for item in results if item[4]
        )
        return results

    def check_socket_transport(kind: str, address: Any):
        context = active_request.get()
        host, port = address_parts(address)
        if mode == "fake" and is_fake_internal_socket(host, port):
            return
        if context is None:
            allowed, capability_reason = internal_socket_capability._authorize(
                host=host, provider_context_present=False,
                attribution=callsite_attribution(),
            )
            if allowed:
                return
            reason = (capability_reason if capability_reason == "CAPABILITY_BUDGET_EXHAUSTED"
                      else "TRANSPORT_NOT_ALLOWED")
            block(kind, None, host, port, reason=reason)
        allowed, reason = transport_allowed(
            context.destination, str(host), normalize_port(port), mode=mode,
            proxy_url=context.proxy_url,
            resolved_transport_hosts=context.resolved_transport_hosts,
        )
        if not allowed:
            block(kind, context.destination, host, port, context.proxy_detected, reason)

    def guarded_connect(sock, address):
        check_socket_transport("socket_connect", address)
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        check_socket_transport("socket_connect_ex", address)
        return original_connect_ex(sock, address)

    stack.enter_context(patch.object(socket.socket, "connect", guarded_connect))
    stack.enter_context(patch.object(socket.socket, "connect_ex", guarded_connect_ex))
    stack.enter_context(patch("socket.getaddrinfo", guarded_getaddrinfo))
    return internal_socket_capability


def _read_map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _find_nested_mapping(root: Any, target_keys: set[str], depth: int = 0) -> list[Mapping[str, Any]]:
    if depth > 8:
        return []
    found: list[Mapping[str, Any]] = []
    if isinstance(root, Mapping):
        if target_keys.intersection(root):
            found.append(root)
        for key, value in root.items():
            if key in {"event", "input", "prompt", "statement", "final_statement", "text", "content"}:
                continue
            if isinstance(value, (Mapping, list)):
                found.extend(_find_nested_mapping(value, target_keys, depth + 1))
    elif isinstance(root, list):
        for value in root[:200]:
            if isinstance(value, (Mapping, list)):
                found.extend(_find_nested_mapping(value, target_keys, depth + 1))
    return found


def _diagnosis_view(claims: list, coverage_rows: list, recommendations: dict,
                    request: dict) -> dict[str, Any]:
    """Project existing decisions to IDs and controlled labels without claim text."""
    by_coverage = {row.get("claim_index"): row for row in coverage_rows
                   if isinstance(row, dict) and type(row.get("claim_index")) is int}
    recommendation_rows = recommendations.get("claim_action_recommendations", [])
    by_action = {row.get("claim_index"): row for row in recommendation_rows
                 if isinstance(row, dict) and type(row.get("claim_index")) is int}
    request_index = request.get("claim_index")
    records = []
    candidates = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        source = claim.get("claim_origin", "writer_draft")
        origin = ("EVENT_FACT_GAP" if source == "event_fact_gap" else
                  "WRITER" if source == "writer_draft" else "UNKNOWN")
        coverage = by_coverage.get(index, {})
        action = by_action.get(index, {})
        records.append({
            "claim_index": index,
            "claim_origin": origin,
            "requires_case_fact": claim.get("requires_case_fact"),
            "requires_legal_rule": claim.get("requires_legal_rule"),
            "coverage_status": coverage.get("case_fact_status"),
            "coverage_reason": coverage.get("case_fact_reason"),
            "action_dependency": (
                action.get("recommended_action") == "REQUEST_HUMAN_FACT_VERIFICATION"
                or (type(request_index) is int and request_index == index)
            ),
            "fact_source_status": "EVENT_ASSERTED" if origin == "EVENT_FACT_GAP" else "UNVERIFIED",
        })
        if origin == "EVENT_FACT_GAP":
            candidates.append({
                "candidate_index": len(candidates), "claim_index": index,
                "candidate_origin": origin, "candidate_type": "UNKNOWN",
                "requires_case_fact": claim.get("requires_case_fact"),
                "requires_legal_rule": claim.get("requires_legal_rule"),
            })

    selected = next((row for row in records if row["claim_index"] == request_index), None)
    dependency = ({
        "request_id": request.get("request_id"),
        "claim_index": request_index,
        "claim_origin": selected["claim_origin"] if selected else "UNKNOWN",
        "coverage_reason": selected["coverage_reason"] if selected else None,
    } if type(request_index) is int else None)
    return {
        "claims": records,
        "event_fact_gap_candidates": candidates,
        "human_fact_dependency": dependency,
        "writer_introduction_status": "WRITER_INTRODUCTION_NOT_OBSERVABLE",
    }


def _extract_case_result(case: Mapping[str, Any], initial: Mapping[str, Any],
                         final: Mapping[str, Any], response_info: Mapping[str, Any],
                         latency_ms: float) -> dict[str, Any]:
    metadata = _read_map(final.get("metadata"))
    results = _read_map(final.get("results")) or _read_map(initial.get("results"))
    legal = _read_map(results.get("legal"))
    legal_meta = _read_map(legal.get("_metadata"))
    rag = _read_map(legal_meta.get("rag"))
    extraction = (_read_map(metadata.get("legal_claim_extraction"))
                  or _read_map(initial.get("legal_claim_extraction"))
                  or _read_map(legal_meta.get("claim_extraction")))
    extraction_telemetry = _read_map(extraction.get("claim_extraction_telemetry"))
    claims = extraction.get("legal_claims") if isinstance(extraction.get("legal_claims"), list) else []
    case_fact_indices = [index for index, claim in enumerate(claims)
                         if _read_map(claim).get("requires_case_fact") is True]
    fact_gap = _read_map(metadata.get("event_fact_gap_detection"))
    if not fact_gap:
        fact_gap = _read_map(extraction.get("event_fact_gap_detection"))
    coverage = _read_map(metadata.get("legal_claim_coverage")) or _read_map(initial.get("legal_claim_coverage"))
    coverage_rows = coverage.get("claim_coverage") if isinstance(coverage.get("claim_coverage"), list) else []
    recommendations = _read_map(metadata.get("legal_claim_action_recommendation"))
    loop = (_read_map(metadata.get("legal_action_loop")) or _read_map(initial.get("legal_action_loop"))
            or _read_map(legal_meta.get("legal_action_loop")))
    loop_actions = loop.get("actions") if isinstance(loop.get("actions"), list) else []
    trace = final.get("trace") if isinstance(final.get("trace"), list) else initial.get("execution_trace", [])
    trace = trace if isinstance(trace, list) else []

    selected_actions: list[str] = []
    observations: list[str] = []
    next_actions: list[str] = []
    decision_telemetry: list[dict[str, Any]] = []
    for item in loop_actions:
        row = _read_map(item)
        selected_actions.append(row.get("selected_action") or row.get("executed_action") or "")
        observations.append(row.get("observation_type") or "")
        next_actions.append(row.get("next_action") or row.get("next_recommended_action") or "")
        if "eligible_action_count" in row or "proposal_status" in row:
            decision_telemetry.append({
                "round": row.get("round", row.get("round_index")),
                "previous_observation_type": row.get("previous_observation_type"),
                "eligible_action_count": row.get("eligible_action_count"),
                "eligible_actions": row.get("eligible_actions", []),
                "eligible_target_claim_indices": row.get("eligible_target_claim_indices", []),
                "deterministic_baseline_action": row.get("deterministic_baseline_action"),
                "deterministic_baseline_target_claim_index": row.get(
                    "deterministic_baseline_target_claim_index"),
                "proposal_called": row.get("proposal_called"),
                "proposal_status": row.get("proposal_status"),
                "proposal_action": row.get("proposal_action"),
                "proposal_reason_code": row.get("proposal_reason_code"),
                "proposal_target_claim_index": row.get("proposal_target_claim_index"),
                "validator_called": row.get("validator_called"),
                "validator_allowed": row.get("validator_allowed"),
                "validator_reason_code": row.get("validator_reason_code"),
                "fallback_used": row.get("proposal_fallback_used", False),
                "fallback_reason_code": row.get("fallback_reason_code"),
                "executed_action": row.get("executed_action", row.get("selected_action")),
                "executed_target_claim_index": row.get("executed_target_claim_index",
                                                          row.get("claim_index")),
                "result_observation_type": row.get("result_observation_type",
                                                     row.get("observation_type")),
                "result_observation_status": row.get("result_observation_status",
                                                       row.get("status", row.get("stop_reason"))),
                "remaining_rounds": (row.get("remaining_budget") or {}).get("rounds"),
                "remaining_tool_calls": (row.get("remaining_budget") or {}).get("tool_calls"),
            })
    for item in trace:
        row = _read_map(item)
        if row.get("agent") == "human_fact":
            selected_actions.append(row.get("action") or "")
            observation = _read_map(row.get("observation"))
            observations.append(observation.get("observation_type") or row.get("reason") or "")
            next_actions.append("")
    selected_actions = [item for item in selected_actions if isinstance(item, str)]
    observations = [item for item in observations if isinstance(item, str)]
    next_actions = [item for item in next_actions if isinstance(item, str)]
    duplicates = sum(max(0, selected_actions.count(action) - 1) for action in set(selected_actions)
                     if action and action not in {"STOP", "STOP_RESOLVED", "STOP_UNRESOLVED", "CONTINUE"})

    request = _read_map(initial.get("human_fact_request"))
    response_sent = _read_map(response_info)
    claim_relations = _read_map(legal_meta.get("claim_relations"))
    source_conflict = claim_relations.get("source_conflict_detected")
    if not isinstance(source_conflict, bool):
        source_conflict = None

    nested = _find_nested_mapping([results, trace], {
        "fallback_used", "timeout_count", "parse_failure_count", "schema_failure_count",
        "provider_error_count", "llm_call_count", "call_count", "prompt_tokens", "total_tokens",
    })
    fallback_agents: list[str] = []
    fallback_count = 0
    timeout_count = parse_failure_count = schema_failure_count = provider_error_count = llm_call_count = None
    for item in nested:
        if item.get("fallback_used") is True:
            fallback_count += 1
            agent = item.get("agent") or item.get("agent_name")
            if isinstance(agent, str) and agent not in fallback_agents:
                fallback_agents.append(agent)
        for field, local_name in (
            ("timeout_count", "timeout_count"), ("parse_failure_count", "parse_failure_count"),
            ("schema_failure_count", "schema_failure_count"), ("provider_error_count", "provider_error_count"),
            ("llm_call_count", "llm_call_count"),
        ):
            value = item.get(field)
            if isinstance(value, int):
                if local_name == "timeout_count": timeout_count = (timeout_count or 0) + value
                elif local_name == "parse_failure_count": parse_failure_count = (parse_failure_count or 0) + value
                elif local_name == "schema_failure_count": schema_failure_count = (schema_failure_count or 0) + value
                elif local_name == "provider_error_count": provider_error_count = (provider_error_count or 0) + value
                else: llm_call_count = (llm_call_count or 0) + value
            elif field == "call_count" and isinstance(value, int):
                llm_call_count = (llm_call_count or 0) + value

    usage_rows = [item for item in nested if any(key in item for key in
                  ("prompt_tokens", "completion_tokens", "total_tokens"))]
    usage = usage_rows[0] if usage_rows else {}
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else None
    completion_tokens = usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else None
    total_tokens = usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None
    usage_available = any(value is not None for value in (prompt_tokens, completion_tokens, total_tokens))

    human_response = _read_map(case.get("human_response"))
    fake_mode = os.getenv("AGENT_MODE", "mock").strip().casefold() == "mock"
    expected = {
        "expected_fact_gap": case.get("expected_fact_gap") if isinstance(case.get("expected_fact_gap"), bool) else None,
        "expected_human_fact_request": (case.get("expected_human_fact_request")
                                        if isinstance(case.get("expected_human_fact_request"), bool) else None),
        "expected_response_type": human_response.get("response_type"),
    }
    return {
        "case_id": case.get("case_id"), "ground_truth": expected,
        "model_provider": "fake" if fake_mode else os.getenv("LLM_PROVIDER", "unknown"),
        "model_name": "deterministic-mock" if fake_mode else os.getenv("LLM_MODEL", "unknown"),
        "runtime_final_state": final.get("status") or final.get("state_status") or initial.get("state_status"),
        "fact_gap": {
            "expected": expected["expected_fact_gap"],
            "detected": (bool(fact_gap.get("candidate_count")) if "candidate_count" in fact_gap
                         else (bool(fact_gap.get("detected")) if isinstance(fact_gap.get("detected"), bool) else None)),
            "claim_count": len(claims), "claim_indices": case_fact_indices,
            "requires_case_fact_count": len(case_fact_indices),
            "requires_legal_rule_count": sum(_read_map(item).get("requires_legal_rule") is True for item in claims),
        },
        "claim_extraction": extraction_telemetry,
        "diagnosis": _diagnosis_view(claims, coverage_rows, recommendations, request),
        "human_fact": {
            "requested": bool(request), "request_count": 1 if request else 0,
            "response_type": response_sent.get("response_type"),
            "response_http_status": response_sent.get("http_status"),
            "resume_result": response_sent.get("resume_result"),
            "final_wait_type": metadata.get("human_wait_type"),
        },
        "legal": {
            "rag_triggered": rag.get("retrieval_executed") if isinstance(rag.get("retrieval_executed"), bool) else None,
            "targeted_retrieval_triggered": any(
                _read_map(item).get("selected_action") == "RETRIEVE_LEGAL_EVIDENCE" for item in loop_actions
            ) if isinstance(loop.get("actions"), list) else None,
            "retrieval_count": rag.get("count") if isinstance(rag.get("count"), int) else None,
            "source_conflict_detected": source_conflict,
        },
        "loop": {
            "round_count": loop.get("round_count") if isinstance(loop.get("round_count"), int) else None,
            "actions": selected_actions, "observation_types": observations,
            "next_actions": next_actions,
            "stop_reason": loop.get("stop_reason") if isinstance(loop.get("stop_reason"), str) else None,
            "duplicate_action_count": duplicates,
            "decision_telemetry": decision_telemetry,
        },
        "reliability": {
            "llm_call_count": llm_call_count, "timeout_count": timeout_count,
            "parse_failure_count": parse_failure_count, "schema_failure_count": schema_failure_count,
            "fallback_count": fallback_count if nested else None, "fallback_agents": fallback_agents,
            "provider_error_count": provider_error_count,
        },
        "trace": {
            "trace_available": bool(trace),
            "diagnostic_fields_available": bool(extraction or loop or fact_gap),
            "trace_safety_passed": True if trace else None,
        },
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": total_tokens, "usage_available": usage_available},
    }


def _case_executor(client, case: Mapping[str, Any]):
    import time

    start = time.perf_counter()
    initial_response = client.post("/api/dynamic/run", json={"event": case["event"]})
    initial = _json_object(initial_response)
    response_info: dict[str, Any] = {"http_status": None, "response_type": None,
                                     "resume_result": None}
    final: Mapping[str, Any] = initial
    session_id = initial.get("session_id")
    if not isinstance(session_id, str):
        raise RuntimeError("Dynamic Runtime response did not include a session_id")

    snapshot_response = client.get(f"/api/dynamic/{session_id}")
    snapshot = _json_object(snapshot_response)
    metadata = _read_map(snapshot.get("metadata"))
    is_fact_input = (snapshot.get("status") == "WAITING_HUMAN"
                     and metadata.get("human_wait_type") == "FACT_INPUT")
    if is_fact_input:
        request = _read_map(initial.get("human_fact_request"))
        ground_truth = _read_map(case.get("human_response"))
        if not request or not ground_truth:
            raise RuntimeError("FACT_INPUT has no frozen Human Fact ground truth")
        payload = {
            "request_id": request.get("request_id"),
            "response_type": ground_truth.get("response_type"),
            "fact_text": ground_truth.get("fact_text", ""),
        }
        response = client.post(
            f"/api/dynamic/{session_id}/fact-response", json=payload,
            headers={"X-User-Id": "semantic-eval-runner", "X-User-Role": "legal_reviewer"},
        )
        response_json = _json_object(response)
        response_info = {
            "http_status": response.status_code,
            "response_type": ground_truth.get("response_type"),
            "resume_result": response_json.get("status"),
        }
    final_response = client.get(f"/api/dynamic/{session_id}")
    final = _json_object(final_response)
    if initial_response.status_code >= 400 or snapshot_response.status_code >= 400 or final_response.status_code >= 400:
        raise RuntimeError("Dynamic Runtime API returned an error status")
    result = _extract_case_result(case, initial, final, response_info,
                                  (time.perf_counter() - start) * 1000)
    result["started_at"] = initial.get("started_at")
    return result


def _json_object(response) -> dict[str, Any]:
    try:
        value = response.json()
    except Exception as exc:
        raise RuntimeError("Dynamic Runtime returned a non-JSON response") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Dynamic Runtime response must be a JSON object")
    return value


def _resolve_real_provider_config():
    # Real mode is an explicit process-level action; a project .env must never
    # silently authorize it. Load credentials only after this check.
    if os.getenv("AGENT_MODE", "").strip().casefold() != "llm":
        raise RuntimeError("Real mode requires AGENT_MODE=llm.")

    load_project_env()
    from backend.config import get_config
    from backend.llm.config import get_llm_config
    from urllib.parse import urlparse

    get_config.cache_clear()
    get_llm_config.cache_clear()
    if not os.getenv("LLM_API_KEY"):
        raise RuntimeError("Real mode requires LLM_API_KEY.")
    app_config = get_config()
    llm_config = get_llm_config()

    if os.getenv("OFFLINE_EVAL", "").strip().casefold() in {"1", "true", "yes", "on"}:
        raise RuntimeError("Real mode refuses OFFLINE_EVAL=true.")

    parsed_base_url = urlparse(llm_config.base_url)
    provider_host = parsed_base_url.hostname
    if (provider_host != "api.deepseek.com" or parsed_base_url.scheme != "https"
            or llm_config.provider != "openai_compatible"
            or not llm_config.model.casefold().startswith("deepseek")):
        raise RuntimeError(
            "Real mode requires HTTPS api.deepseek.com with openai_compatible and a DeepSeek model."
        )
    return app_config, llm_config, provider_host


def run_validation(
    *, mode: str = "fake", output_dir: Path = DEFAULT_REPORT_DIR,
    continue_on_error: bool = False, confirm_real_provider: bool = False,
    case_id: str | None = None, app=None,
) -> tuple[dict[str, Any], Path, list[dict[str, str]]]:
    if mode not in {"fake", "real"}:
        raise ValueError("mode must be fake or real")
    if mode == "real" and not confirm_real_provider:
        raise RuntimeError("Real mode requires explicit confirm_real_provider=True.")
    cases, frozen_hash = load_frozen_cases()
    if case_id is not None:
        if case_id not in DEFAULT_CASE_IDS:
            raise ValueError(f"Case {case_id!r} is not in the fixed frozen evaluation slice")
        cases = [case for case in cases if case["case_id"] == case_id]
    case_ids = [case["case_id"] for case in cases]
    from evaluation.real_llm_eval_harness import RealLLMEvalRun, collect_run_metadata

    if mode == "fake":
        temporary = tempfile.TemporaryDirectory(prefix="crisisagent-semantic-runtime-")
        temp_root = Path(temporary.name)
        env_patch = patch.dict(os.environ, _fake_environment(temp_root), clear=False)
        provider_host = None
        provider = "fake"
        model = "deterministic-mock"
        external_allowed = False
    else:
        app_config, llm_config, provider_host = _resolve_real_provider_config()
        temporary = tempfile.TemporaryDirectory(prefix="crisisagent-semantic-runtime-")
        temp_root = Path(temporary.name)
        env_patch = patch.dict(os.environ, _fake_environment(temp_root) | {
            "AGENT_MODE": app_config.agent_mode, "OFFLINE_EVAL": "0",
            "LLM_BASE_URL": llm_config.base_url, "LLM_API_KEY": llm_config.api_key,
            "LLM_MODEL": llm_config.model, "LLM_PROVIDER": llm_config.provider,
        }, clear=False)
        provider = llm_config.provider
        model = llm_config.model
        external_allowed = True

    metadata = collect_run_metadata(
        frozen_file="evaluation/dynamic_real_case_v1.json", frozen_sha256=frozen_hash,
        selected_case_ids=case_ids, provider=provider, model=model,
        external_provider_allowed=external_allowed, other_external_network_allowed=False,
        repo_root=ROOT,
    )
    metadata["AGENT_MODE"] = "mock" if mode == "fake" else "llm"
    metadata["OFFLINE_EVAL"] = "1" if mode == "fake" else os.getenv("OFFLINE_EVAL", "0")
    run = RealLLMEvalRun(output_dir, metadata)
    attempts: list[dict[str, Any]] = []
    diagnostics_path = run.jsonl_path.with_name(run.jsonl_path.stem + "_network_diagnostics.jsonl")
    diagnostics_created = False

    def persist_diagnostic(diagnostic: Mapping[str, Any]) -> None:
        nonlocal diagnostics_created
        if not diagnostics_created:
            with diagnostics_path.open("x", encoding="utf-8", newline="\n"):
                pass
            diagnostics_created = True
        with diagnostics_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(dict(diagnostic), ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    try:
        with env_patch:
            from backend.core.checkpoint import JSONCheckpointRepository
            from backend.core import human_fact_resume
            from backend.config import get_config
            from backend.llm.config import get_llm_config
            import backend.main as main_module
            from fastapi.testclient import TestClient

            get_config.cache_clear()
            get_llm_config.cache_clear()

            checkpoint_repo = JSONCheckpointRepository(temp_root / "checkpoints.json")
            with ExitStack() as stack:
                stack.enter_context(patch.object(main_module, "save_checkpoint", checkpoint_repo.save_checkpoint))
                stack.enter_context(patch.object(main_module, "load_checkpoint", checkpoint_repo.load_checkpoint))
                stack.enter_context(patch.object(human_fact_resume, "save_checkpoint", checkpoint_repo.save_checkpoint))
                stack.enter_context(patch.object(human_fact_resume, "load_checkpoint", checkpoint_repo.load_checkpoint))
                internal_socket_capability = _network_guard(
                    stack, mode, provider_host, attempts, persist_diagnostic,
                )

                from backend.llm.offline_guard import assert_offline_eval_startup
                if mode == "fake":
                    guard = assert_offline_eval_startup()
                    if guard.get("external_llm_allowed") is not False:
                        raise RuntimeError("Fake mode failed its offline startup assertion")
                app_to_use = app or main_module.app
                client = TestClient(app_to_use)
                api_client = _CapabilityScopedClient(client, internal_socket_capability)
                try:
                    def execute(case):
                        result = _case_executor(api_client, case)
                        if attempts:
                            raise ExternalRequestBlocked(attempts[0])
                        return result

                    summary = run.run_cases(cases, execute, continue_on_error=continue_on_error)
                finally:
                    client.close()
    finally:
        temporary.cleanup()
    return summary, run.jsonl_path, attempts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fake", "real"), default="fake")
    parser.add_argument("--case-id", choices=DEFAULT_CASE_IDS,
                        help="Run one case from the fixed frozen evaluation slice.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Continue with the next frozen case after writing an ERROR record.")
    parser.add_argument("--confirm-real-provider", action="store_true",
                        help="Required explicit confirmation before any authorized DeepSeek request.")
    args = parser.parse_args(argv)
    if args.mode == "real" and not args.confirm_real_provider:
        parser.error("--mode real requires --confirm-real-provider; no request was made")
    summary, jsonl_path, attempts = run_validation(
        mode=args.mode, output_dir=args.output_dir, continue_on_error=args.continue_on_error,
        confirm_real_provider=args.confirm_real_provider, case_id=args.case_id,
    )
    diagnostics_path = jsonl_path.with_name(jsonl_path.stem + "_network_diagnostics.jsonl")
    print(json.dumps({"mode": args.mode, "summary": summary, "jsonl_path": str(jsonl_path),
                      "network_diagnostics_path": str(diagnostics_path) if diagnostics_path.exists() else None,
                      "external_request_attempts_blocked": len(attempts)}, ensure_ascii=False))
    return 1 if attempts or summary.get("error_cases") else 0


if __name__ == "__main__":
    raise SystemExit(main())
