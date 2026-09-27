from __future__ import annotations

import asyncio
import json
import secrets
import importlib

import pytest
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.security.model_service import ModelServiceMiddleware, max_upload_bytes
from app.security.service_token import service_headers


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("OMNIX_MAX_UPLOAD_BYTES", "512")
    monkeypatch.delenv("OMNIX_ALLOWED_HOSTS", raising=False)
    app = FastAPI()
    app.add_middleware(ModelServiceMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.api_route("/action", methods=["GET", "POST"])
    async def action(request: Request):
        return {"bytes": len(await request.body())}

    @app.post("/caught")
    async def caught(request: Request):
        try:
            await request.body()
        except Exception:
            return {"ok": True}

    @app.post("/multipart")
    async def multipart(file: UploadFile):
        return {"bytes": len(await file.read())}

    @app.get("/error")
    def error():
        raise HTTPException(500, "Traceback: private provider path and credential")

    @app.get("/unhandled")
    def unhandled():
        raise RuntimeError("Traceback: private provider path and credential")

    @app.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        await socket.send_text(await socket.receive_text())
        await socket.close()

    return app, TestClient(app, base_url="http://127.0.0.1"), service_headers()


def assert_error(response, status, code):
    assert response.status_code == status
    assert set(response.json()) == {"error", "request_id"}
    assert response.json()["error"] == code
    assert len(response.json()["request_id"]) >= 24
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert "Traceback" not in response.text
    assert "credential" not in response.text


def test_all_nonhealth_routes_require_the_issued_token(protected):
    _, client, headers = protected
    assert client.get("/health").status_code == 200
    for path in ("/action", "/docs", "/openapi.json", "/health/", "/unknown"):
        assert_error(client.get(path), 401, "invalid_service_token")
    assert_error(client.post("/health", headers={"X-Omnix-Client": "test"}), 401, "invalid_service_token")
    assert client.get("/action", headers=headers).status_code == 200
    assert_error(client.get("/action", headers={"X-Omnix-Service-Token": secrets.token_urlsafe(32)}), 401, "invalid_service_token")
    assert_error(client.get("/action", headers=[("X-Omnix-Service-Token", headers["X-Omnix-Service-Token"])] * 2), 401, "invalid_service_token")


def test_missing_server_configuration_fails_closed(protected, monkeypatch):
    _, client, headers = protected
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN")
    assert_error(client.get("/action", headers=headers), 401, "invalid_service_token")
    with pytest.raises(RuntimeError, match="service_credential_unavailable"):
        service_headers()


def test_error_envelope_replaces_provider_and_guard_errors(protected):
    _, client, headers = protected
    for path in ("/error", "/unhandled"):
        assert_error(client.get(path, headers=headers), 500, "model_service_error")
    assert_error(client.get("/health", headers={"Host": "evil.test"}), 421, "disallowed_host")
    assert_error(client.post("/action", headers={"X-Omnix-Service-Token": headers["X-Omnix-Service-Token"]}), 403, "forbidden")
    assert_error(client.get("/unknown", headers=headers), 404, "not_found")


def test_authentication_precedes_content_length_limit(protected):
    _, client, headers = protected
    assert_error(client.post("/action", content=b"x" * 513, headers={"X-Omnix-Client": "test"}), 401, "invalid_service_token")
    assert_error(client.post("/action", content=b"x" * 513, headers=headers), 413, "upload_too_large")
    assert client.post("/action", content=b"x" * 512, headers=headers).json() == {"bytes": 512}


def test_multipart_upload_limit(protected):
    _, client, headers = protected
    assert client.post("/multipart", files={"file": ("audio.wav", b"x" * 100)}, headers=headers).status_code == 200
    assert_error(client.post("/multipart", files={"file": ("audio.wav", b"x" * 512)}, headers=headers), 413, "upload_too_large")


@pytest.mark.parametrize("path", ["/action", "/caught", "/multipart"])
@pytest.mark.parametrize("length", [None, b"1"])
def test_chunked_and_underreported_uploads_stay_bounded(protected, path, length):
    app, _, headers = protected
    chunks = [b"x" * 256, b"x" * 256, b"x", b"must not be read"]
    consumed = []
    messages = []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "server": ("127.0.0.1", 80),
             "client": ("127.0.0.1", 1234),
             "headers": [(b"host", b"127.0.0.1"),
                         *[(k.lower().encode(), v.encode()) for k, v in headers.items()]]}
    if length is not None:
        scope["headers"].append((b"content-length", length))
    if path == "/multipart":
        prefix = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n\r\n'
        chunks[0] = prefix + b"x" * (256 - len(prefix))
        scope["headers"].append((b"content-type", b"multipart/form-data; boundary=boundary"))

    async def receive():
        chunk = chunks[len(consumed)]
        consumed.append(chunk)
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    assert len(consumed) == 3
    assert messages[0]["status"] == 413
    assert json.loads(messages[1]["body"])["error"] == "upload_too_large"


def test_websocket_authentication_and_message_budget(protected):
    _, client, headers = protected
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("ws://127.0.0.1/ws"):
            pass
    assert error.value.code == 1008
    with client.websocket_connect("ws://127.0.0.1/ws", headers=headers) as socket:
        socket.send_text("ok")
        assert socket.receive_text() == "ok"
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("ws://127.0.0.1/ws", headers=headers) as socket:
            socket.send_text("x" * 513)
            socket.receive_text()
    assert error.value.code == 1009


@pytest.mark.parametrize("raw", ["", "0", "-1", "1.5", " 123", "infinite", "\u0661"])
def test_invalid_upload_configuration_fails_closed(monkeypatch, raw):
    monkeypatch.setenv("OMNIX_MAX_UPLOAD_BYTES", raw)
    with pytest.raises(ValueError, match="positive integer"):
        max_upload_bytes()


@pytest.mark.parametrize("module", ["tts_server", "nemotron_eou_stt_server", "openai_api", "app.image_service_runtime"])
def test_every_composed_model_route_is_authenticated(monkeypatch, module):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    app = importlib.import_module(module).app
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    checked = 0
    for route in app.routes:
        if not getattr(route, "methods", None) or route.path == "/health":
            continue
        for method in route.methods:
            response = client.request(method, route.path)
            if method == "HEAD":
                assert response.status_code == 401
                assert len(response.headers["x-request-id"]) >= 24
                assert response.content == b""
            else:
                assert_error(response, 401, "invalid_service_token")
            checked += 1
    assert checked >= 4


def test_health_does_not_expose_provider_failure(monkeypatch):
    import tts_server
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", None)
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "Traceback: private path and credential")
    response = TestClient(tts_server.app, base_url="http://127.0.0.1").get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"] == "model_unavailable"
    assert "Traceback" not in response.text
    assert "private" not in response.text


def test_openai_stream_failure_keeps_error_details_private_and_correlates_request(monkeypatch):
    import openai_api
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)

    def broken_chunk(**_kwargs):
        raise RuntimeError(f"Traceback: private credential {token}")

    monkeypatch.setattr(openai_api, "ChatStreamResponse", broken_chunk)
    client = TestClient(openai_api.app, base_url="http://127.0.0.1", headers=service_headers())
    response = client.post("/v1/chat/completions", json={"model": "test", "messages": [{"role": "user", "content": "test"}], "stream": True})
    assert response.status_code == 200
    payload = json.loads(response.text.removeprefix("data: ").strip())
    assert payload == {"error": "model_service_error", "request_id": response.headers["x-request-id"]}
    assert token not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("request_id", ["server-request-identifier", None])
def test_stt_background_feed_failure_reports_private_correlated_error(request_id):
    from app.providers.nemotron_eou_live_websocket import HybridSegment, _schedule_stream_drain

    class Socket:
        scope = {"state": {"request_id": request_id} if request_id else {}}

        def __init__(self):
            self.messages = []

        async def send_json(self, payload):
            self.messages.append(payload)

    class BrokenManager:
        feed_chunk_samples = 1

        def feed(self, *_args):
            raise RuntimeError("private provider details")

    async def run():
        socket = Socket()
        segment = HybridSegment("test-segment", 1, 0, 0)
        segment.stream_pending.extend(b"\x00\x00")
        _schedule_stream_drain(segment, BrokenManager(), socket, asyncio.Lock())
        task = segment.stream_task
        assert task is not None
        await task
        assert segment.stream_task is None
        assert len(socket.messages) == 1
        message = socket.messages[0]
        assert message["type"] == "segment_error"
        assert message["error"] == message["errorCode"] == "model_service_error"
        assert message["request_id"] == request_id if request_id else len(message["request_id"]) == 32
        assert "private provider details" not in json.dumps(message)

    asyncio.run(run())
