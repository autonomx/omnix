"""Pooled HTTP client: retries, circuit breaker and cancellation (WP-7.2)."""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.runtime.cancellation import CancellationToken, OperationCancelled
from app.runtime.http_client import CircuitOpenError, HttpPolicy, PooledHttpClient

FAST = HttpPolicy(backoff_seconds=0.001, max_backoff_seconds=0.002, circuit_failures=3, circuit_cooldown_seconds=0.05)


def _client(handler, policy: HttpPolicy = FAST) -> PooledHttpClient:
    return PooledHttpClient("test", policy, transport=httpx.MockTransport(handler))


def _scripted(*responses):
    """A transport handler replaying ``responses`` (statuses, headers or exceptions)."""
    calls: list[httpx.Request] = []
    script = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        item = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(item, Exception):
            raise item
        status, headers = item if isinstance(item, tuple) else (item, {})
        return httpx.Response(status, headers=headers, json={"status": status})

    return handle, calls


def test_a_503_is_retried_then_succeeds() -> None:
    handle, calls = _scripted(503, 200)

    response = _client(handle).post("http://provider/v1/chat", json={})

    assert response.status_code == 200
    assert len(calls) == 2


def test_a_non_idempotent_call_is_not_retried_on_500_or_connection_errors() -> None:
    handle, calls = _scripted(500)
    assert _client(handle).post("http://provider/v1/chat").status_code == 500
    assert len(calls) == 1

    handle, calls = _scripted(httpx.ConnectError("refused"))
    with pytest.raises(httpx.ConnectError):
        _client(handle).post("http://provider/v1/chat")
    assert len(calls) == 1


def test_idempotent_calls_retry_connection_errors() -> None:
    handle, calls = _scripted(httpx.ConnectError("refused"), 200)

    assert _client(handle).get("http://provider/health").status_code == 200
    assert len(calls) == 2


def test_retry_false_disables_even_429_and_503_retries() -> None:
    handle, calls = _scripted(503, 200)

    assert _client(handle).post("http://provider/v1/chat", retry=False).status_code == 503
    assert len(calls) == 1


def test_retry_after_is_honoured_unless_it_is_too_long() -> None:
    handle, calls = _scripted((429, {"Retry-After": "0"}), 200)
    assert _client(handle).post("http://provider/v1/chat").status_code == 200
    assert len(calls) == 2

    handle, calls = _scripted((429, {"Retry-After": "120"}), 200)
    response = _client(handle).post("http://provider/v1/chat")
    assert response.status_code == 429  # not waited out; the caller decides
    assert len(calls) == 1


def test_the_circuit_opens_after_repeated_failures_and_a_probe_closes_it() -> None:
    handle, calls = _scripted(httpx.ConnectError("down"))
    client = _client(handle, HttpPolicy(max_retries=0, circuit_failures=3, circuit_cooldown_seconds=0.05))

    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            client.get("http://provider/health")
    with pytest.raises(CircuitOpenError):
        client.get("http://provider/health")
    assert len(calls) == 3  # the open circuit did not reach the provider
    assert client.circuit.state == "open"

    healed, healed_calls = _scripted(200)
    client._client._transport = httpx.MockTransport(healed)
    deadline = time.monotonic() + 1
    while client.circuit.state == "open" and time.monotonic() < deadline:
        threading.Event().wait(0.01)
    assert client.get("http://provider/health").status_code == 200
    assert client.circuit.state == "closed"
    assert len(healed_calls) == 1


def test_a_cancel_during_backoff_returns_at_once() -> None:
    handle, _calls = _scripted(503)
    client = _client(handle, HttpPolicy(backoff_seconds=5.0, max_backoff_seconds=5.0))
    token = CancellationToken()
    threading.Timer(0.05, token.cancel).start()

    started = time.perf_counter()
    with pytest.raises(OperationCancelled):
        client.post("http://provider/v1/chat", cancel=token)
    assert time.perf_counter() - started < 1.0


class _StallingStream(BaseHTTPRequestHandler):
    """Sends one chunk of a streamed body, then waits until released."""

    release = threading.Event()

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(b"6\r\ndata 1\r\n")
        self.wfile.flush()
        self.release.wait(5)

    def log_message(self, *args) -> None:
        return


def test_a_cancel_stops_a_stalled_stream_within_200_ms() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StallingStream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = PooledHttpClient("stream", HttpPolicy(read_seconds=10))
    token = CancellationToken()
    received: list[bytes] = []
    try:
        with pytest.raises(OperationCancelled):
            with client.stream("GET", f"http://127.0.0.1:{server.server_port}/events", cancel=token) as response:
                for chunk in response.iter_raw():
                    received.append(chunk)
                    cancelled_at = time.perf_counter()
                    threading.Timer(0.0, token.cancel).start()
        stopped_after = time.perf_counter() - cancelled_at
    finally:
        _StallingStream.release.set()
        client.close()
        server.shutdown()
        server.server_close()

    assert received == [b"data 1"]
    assert stopped_after < 0.2


def _provider_samples(client: str) -> dict[tuple[str, str], float]:
    from app.observability.metrics import exposition

    samples: dict[tuple[str, str], float] = {}
    for line in exposition()[0].decode().splitlines():
        for metric in ("omnix_provider_calls_total", "omnix_provider_retries_total", "omnix_provider_response_seconds_count"):
            if line.startswith(metric + "{") and f'client="{client}"' in line:
                outcome = line.split('outcome="')[1].split('"')[0] if 'outcome="' in line else ""
                samples[(metric, outcome)] = float(line.split()[-1])
    return samples


@pytest.fixture
def provider_metrics():
    from app.observability.metrics import install_provider_metrics
    from app.runtime.http_client import set_attempt_observers

    install_provider_metrics()
    yield
    set_attempt_observers(None, None)


def test_without_observers_attempts_are_not_reported() -> None:
    from app.runtime.http_client import set_attempt_observers

    set_attempt_observers(None, None)
    handle, _ = _scripted(200)
    PooledHttpClient("metrics-unobserved", FAST, transport=httpx.MockTransport(handle)).get("http://provider/")

    assert _provider_samples("metrics-unobserved") == {}


def test_attempts_retries_and_latency_are_recorded_per_client(provider_metrics) -> None:
    handle, _ = _scripted(503, 200, httpx.ConnectError("refused"))
    client = PooledHttpClient("metrics-probe", FAST, transport=httpx.MockTransport(handle))

    client.post("http://provider/v1/chat", json={})
    with pytest.raises(httpx.ConnectError):
        client.post("http://provider/v1/chat", json={})

    samples = _provider_samples("metrics-probe")
    assert samples[("omnix_provider_calls_total", "5xx")] == 1
    assert samples[("omnix_provider_calls_total", "2xx")] == 1
    assert samples[("omnix_provider_calls_total", "transport_error")] == 1
    assert samples[("omnix_provider_retries_total", "")] == 1
    assert samples[("omnix_provider_response_seconds_count", "")] == 3


def test_a_call_refused_by_the_open_circuit_is_counted(provider_metrics) -> None:
    handle, _ = _scripted(500)
    client = PooledHttpClient(
        "metrics-circuit", HttpPolicy(max_retries=0, circuit_failures=1, circuit_cooldown_seconds=60),
        transport=httpx.MockTransport(handle),
    )
    client.post("http://provider/v1/chat", json={})

    with pytest.raises(CircuitOpenError):
        client.post("http://provider/v1/chat", json={})

    assert _provider_samples("metrics-circuit")[("omnix_provider_calls_total", "circuit_open")] == 1


def test_recording_is_a_no_op_without_prometheus_client(monkeypatch) -> None:
    from app.observability import metrics

    def missing():
        raise ImportError("prometheus_client")

    monkeypatch.setattr(metrics, "_metrics", None)
    monkeypatch.setattr(metrics, "_build", missing)

    metrics.record_provider_attempt("tts-service", "2xx", 0.1)
    metrics.record_provider_retry("tts-service")
    assert metrics.request_snapshot() == {"active_requests": 0, "request_count": 0, "error_count": 0}
