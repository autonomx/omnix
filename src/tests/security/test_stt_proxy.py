from __future__ import annotations

import asyncio
import json
import secrets

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from websockets.exceptions import SecurityError

from app.gateway import stt_proxy_routes as proxy
from app.security.model_service import ModelServiceMiddleware
from app.security.request_guard import RequestGuardMiddleware


@pytest.fixture
def setup(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    monkeypatch.setenv("OMNIX_MAX_UPLOAD_BYTES", "1024")
    monkeypatch.setattr(proxy, "_stt_base_url", lambda: "http://127.0.0.1:5201/private")
    app = FastAPI()
    app.add_middleware(RequestGuardMiddleware)
    proxy.register_stt_proxy_routes(app)
    upstream = FastAPI()
    upstream.add_middleware(ModelServiceMiddleware)
    calls = []

    @upstream.api_route("/private/authorityz", methods=["GET"])
    @upstream.api_route("/private/transcribe", methods=["POST"])
    async def endpoint(request: Request):
        body = await request.body()
        calls.append((request, body))
        return {"ok": True, "eligible": True, "text": "hello"}

    real_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return real_client(transport=httpx.ASGITransport(app=upstream), **kwargs)

    # Patch only the proxy's factory via a local namespace, not httpx globally.
    from types import SimpleNamespace
    monkeypatch.setattr(proxy, "httpx", SimpleNamespace(AsyncClient=client, HTTPError=httpx.HTTPError))
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "web"}), calls, token


def test_authority_uses_configured_target_and_private_credential(setup):
    client, calls, token = setup
    response = client.get("/api/stt/authorityz?language=en&mode=test&url=https://evil.test",
                          headers={"X-Omnix-Service-Token": "browser-forged", "Authorization": "browser-auth"})
    assert response.status_code == 200
    request, body = calls[0]
    assert request.headers["x-omnix-service-token"] == token
    assert "authorization" not in request.headers
    assert dict(request.query_params) == {"language": "en", "mode": "test"}
    assert request.url.path == "/private/authorityz"
    assert body == b""
    assert token not in response.text


def test_transcription_upload_is_forwarded_without_browser_credentials(setup):
    client, calls, token = setup
    response = client.post("/api/stt/transcribe", files={"audio": ("voice.wav", b"samples")},
                           headers={"Cookie": "browser-cookie", "X-Omnix-Service-Token": "forged"})
    assert response.status_code == 200
    request, body = calls[0]
    assert request.headers["x-omnix-service-token"] == token
    assert "cookie" not in request.headers
    assert b"samples" in body


def test_upload_limit_does_not_contact_the_model(setup):
    client, calls, _ = setup
    response = client.post("/api/stt/transcribe", files={"audio": ("voice.wav", b"x" * 1024)})
    assert response.status_code == 413
    assert response.json()["error"] == "upload_too_large"
    assert calls == []


def test_chunked_upload_limit_is_enforced_as_it_is_forwarded(setup):
    client, calls, _ = setup
    response = client.post("/api/stt/transcribe", content=iter([b"x" * 512, b"x" * 512, b"x"]),
                           headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413
    assert calls == []


@pytest.mark.parametrize("query", ["mode=unknown", "language=../private", "language=" + "a" * 33])
def test_invalid_probe_parameters_do_not_contact_the_model(setup, query):
    client, calls, _ = setup
    assert client.get(f"/api/stt/authorityz?{query}").status_code == 422
    assert calls == []


def test_missing_credential_fails_without_contacting_sidecar(setup, monkeypatch):
    client, calls, _ = setup
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN")
    response = client.get("/api/stt/authorityz")
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize("status", [307, 401, 500])
def test_upstream_errors_and_redirects_are_not_forwarded(setup, monkeypatch, status):
    client, _, token = setup
    request_count = 0

    def handler(request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(status, text=f"Traceback: private {token}",
                              headers={"Location": "https://evil.test"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    response = client.get("/api/stt/authorityz")
    assert response.status_code == 503
    assert request_count == 1
    assert set(response.json()) == {"error", "request_id"}
    assert "Traceback" not in response.text
    assert token not in response.text
    assert "location" not in response.headers


def test_service_websocket_rejects_redirects_without_reporting_uri():
    async def check():
        connection = proxy._ServiceConnect("ws://127.0.0.1:5201/ws/transcribe")
        with pytest.raises(SecurityError, match="^model_service_redirect_rejected$"):
            connection.handle_redirect("ws://evil.test/private")
    asyncio.run(check())


def test_websocket_proxy_uses_private_headers_and_cleans_up_on_disconnect(setup, monkeypatch):
    client, _, token = setup
    captured = {}
    stopped = []

    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, message):
            await self.queue.put(message)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return await self.queue.get()
            except asyncio.CancelledError:
                stopped.append("receiver_cancelled")
                raise

    class Connection:
        def __init__(self, uri, **kwargs):
            captured.update(uri=uri, **kwargs)

        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_args):
            stopped.append("upstream_closed")

    monkeypatch.setattr(proxy, "_ServiceConnect", Connection)
    with client.websocket_connect("ws://127.0.0.1/api/stt/ws/transcribe?language=en&url=ws://evil.test",
                                  headers={"Origin": "http://localhost:5173", "X-Omnix-Service-Token": "forged"}) as socket:
        socket.send_text(json.dumps({"type": "session_start"}))
        assert socket.receive_json() == {"type": "session_start"}
        socket.send_bytes(b"pcm")
        assert socket.receive_bytes() == b"pcm"
    assert captured["uri"] == "ws://127.0.0.1:5201/private/ws/transcribe?language=en"
    assert captured["extra_headers"]["X-Omnix-Service-Token"] == token
    assert captured["max_queue"] == 8
    assert stopped == ["receiver_cancelled", "upstream_closed"]
