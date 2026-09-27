"""Actual HTTP transport coverage for sidecar credentials and redirect containment."""
from __future__ import annotations

import io
import json
import secrets
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import image_http_client, tts_http_client
from app.providers.qwen_http_gateway import QwenHttpGatewayProvider
from app.jobs import provider_control


@pytest.fixture
def sidecar(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    calls = []
    state = {"redirect": False}
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\0" * 240)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.path, self.headers.get("X-Omnix-Service-Token"), body))
            if state["redirect"] and self.path != "/redirect-target":
                self.send_response(307)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            binary = self.path.endswith("/generate_stream_audio")
            data = output.getvalue() if binary else json.dumps({"success": True, "speakers": ["one"], "ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav" if binary else "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(tts_http_client, "_tts_base_url", lambda: url)
    monkeypatch.setenv("OMNIX_IMAGE_URL", url)
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    try:
        yield url, calls, state, token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _call(name, url):
    if name == "speakers":
        return tts_http_client.tts_speakers()
    if name == "audio":
        return tts_http_client.tts_generate_audio(text="hello", speaker="one")
    if name == "stream":
        return tts_http_client.tts_generate_stream_audio(text="hello", speaker="one")
    if name == "clone":
        return tts_http_client.tts_voice_clone(voice_id="test", audio_bytes=b"owned test audio")
    if name == "qwen_speakers":
        return QwenHttpGatewayProvider(url).get_speakers()
    if name == "qwen_audio":
        return QwenHttpGatewayProvider(url).generate_audio("hello")
    if name == "qwen_stream":
        return list(QwenHttpGatewayProvider(url).generate_audio_stream("hello"))
    if name == "image_read":
        return image_http_client.request_image_service("GET", "/provider/status")
    if name == "worker_control":
        return provider_control._post_json(url + "/provider/load", {"provider": "test"}, 2)
    return image_http_client.request_image_service("POST", "/generate", {"prompt": "test"})


_CALLERS = ["speakers", "audio", "stream", "clone", "qwen_speakers", "qwen_audio", "qwen_stream", "image_read", "image_write", "worker_control"]


@pytest.mark.parametrize("name", _CALLERS)
def test_gateway_sidecar_clients_send_the_issued_credential(sidecar, name):
    url, calls, _, token = sidecar
    _call(name, url)
    assert len(calls) == 1
    assert calls[0][1] == token


@pytest.mark.parametrize("name", _CALLERS)
def test_credentials_are_never_forwarded_through_redirects(sidecar, name):
    url, calls, state, _ = sidecar
    state["redirect"] = True
    try:
        _call(name, url)
    except (ValueError, RuntimeError, EOFError, wave.Error):
        pass
    assert len(calls) == 1
    assert calls[0][0] != "/redirect-target"


def test_worker_job_input_cannot_choose_a_credential_audience(monkeypatch):
    from app.jobs.models import JobRecord, JobStatus, ResourceClass
    from app.jobs.residency import ModelResidencyRecord, ModelResidencyStatus
    job = JobRecord(id="test", module="image", type="model_load", status=JobStatus.QUEUED,
                    resource_class=ResourceClass.GPU_IMAGE, created_at="test", updated_at="test",
                    input_payload={"worker_endpoint": "http://evil.test"})
    record = ModelResidencyRecord(model_id="image:test", model_name="test", provider_id="image:test",
                                  module="image", resource_class=ResourceClass.GPU_IMAGE,
                                  status=ModelResidencyStatus.LOADING, worker_id="test")
    with pytest.raises(RuntimeError, match="endpoint_not_configured"):
        provider_control.load_worker_model(record, job, post_json=lambda *_args: pytest.fail("untrusted target contacted"))
