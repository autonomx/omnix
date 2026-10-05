from __future__ import annotations

from contextlib import contextmanager

import asyncio
import threading
import pytest
import secrets

from app.security.service_token import service_headers
import io
import wave
from typing import Any, Dict, Iterable, Tuple

from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def issued_service_token(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))


def test_initialize_tts_provider_passes_config(monkeypatch):
    from services.tts import tts_server

    captured: Dict[str, Any] = {}

    class FakeProvider:
        def __init__(self, config):
            captured["config"] = dict(config)
            self.provider_name = "qwen3_tts"
            self.device = config.get("device", "cpu")
            self._model_config = dict(config)

    fake_settings = {
        "faster-qwen3-tts": {
            "model_name": "Qwen/Qwen3-TTS-0.6B",
            "device": "cuda",
        }
    }

    def fake_load_settings():
        return fake_settings

    monkeypatch.setattr("app.settings.access.load_settings", fake_load_settings)
    monkeypatch.setattr(
        "app.providers.faster_qwen3_tts_provider.FasterQwen3TTSProvider",
        FakeProvider,
        raising=False,
    )

    provider = tts_server._load_qwen3_provider()

    assert provider is not None
    assert captured["config"]["model_name"] == "Qwen/Qwen3-TTS-0.6B"
    assert captured["config"]["device"] == "cuda"


def test_get_tts_service_status_returns_ready_details():
    from services.tts import tts_server

    class FakeProvider:
        provider_name = "qwen3_tts"
        device = "cuda"
        _model_config = {"model_name": "Qwen/Qwen3-TTS-0.6B"}

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        result = tts_server.get_tts_service_status()
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert result["ok"] is True
    assert result["provider"] == "qwen3_tts"
    assert result["details"]["provider_class"] == "FakeProvider"
    assert result["details"]["configured_model"] == "Qwen/Qwen3-TTS-0.6B"
    assert result["details"]["configured_device"] == "cuda"


def test_generate_stream_audio_returns_chunks_on_success():
    from services.tts import tts_server

    class FakeProvider:
        def generate_audio_stream(
            self,
            *,
            text: str,
            speaker: str,
            language: str,
            **_: Any,
        ) -> Iterable[Tuple[bytes, int, Dict[str, Any]]]:
            assert text == "hello world"
            assert speaker == "default"
            assert language == "en"
            import numpy as np
            yield (np.array([0.0, 0.1, 0.2], dtype=np.float32), 24000, {"chunk_index": 0})

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())

        response = client.post(
            "/api/tts/generate_stream_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    with wave.open(io.BytesIO(response.content), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnframes() == 3


def test_generate_stream_audio_surfaces_missing_sox_error():
    from services.tts import tts_server

    class FakeProvider:
        def generate_audio_stream(self, **_: Any):
            raise RuntimeError("Model loading failed: No module named 'sox'")

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())

        response = client.post(
            "/api/tts/generate_stream_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "model_service_error"
    assert set(payload) == {"error", "request_id"}
    assert "sox" not in response.text
    assert "Traceback" not in response.text
    assert "traceback" not in payload


def test_generate_audio_surfaces_missing_sox_error():
    from services.tts import tts_server

    class FakeProvider:
        def generate_audio(self, **_: Any):
            raise RuntimeError("Model loading failed: No module named 'sox'")

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())

        response = client.post(
            "/api/tts/generate_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "model_service_error"
    assert set(payload) == {"error", "request_id"}
    assert "sox" not in response.text
    assert "Traceback" not in response.text


def test_live_call_endpoint_streams_binary_pcm_while_holding_device_permit(monkeypatch):
    import numpy as np
    from services.tts import tts_server

    events = []

    class FakeProvider:
        def generate_audio_stream(self, **kwargs):
            assert kwargs["_device_permit_held"] is True
            return iter(((np.array([0.0, 0.5, -0.5], dtype=np.float32), 24000, {}),))

    @contextmanager
    def permit_slot(*_args, **_kwargs):
        events.append("acquired")
        try:
            yield object()
        finally:
            events.append("released")

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", FakeProvider())
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "")
    monkeypatch.setattr(tts_server, "device_permit_slot", permit_slot)
    client = TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())

    response = client.post(
        "/api/tts/live-call/stream",
        json={"text": "hello world", "speaker": "default", "language": "en"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-omnix-pcm16")
    assert response.headers["x-omnix-audio-format"] == "pcm_s16le"
    assert response.headers["x-omnix-sample-rate"] == "24000"
    assert len(response.content) == 6
    assert events == ["acquired", "released"]


def test_live_call_endpoint_rejects_saturation_with_retry_after(monkeypatch):
    from contextlib import contextmanager

    from services.tts import tts_server
    from app.persistence.device_permits import DevicePermitUnavailable

    class FakeProvider:
        def generate_audio_stream(self, **_kwargs):
            raise AssertionError("saturated admission must not start provider work")

    @contextmanager
    def unavailable(*_args, **_kwargs):
        raise DevicePermitUnavailable("busy")
        yield

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", FakeProvider())
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "")
    monkeypatch.setattr(tts_server, "device_permit_slot", unavailable)
    client = TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())

    response = client.post(
        "/api/tts/live-call/stream",
        json={"text": "hello world", "speaker": "default", "language": "en"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"
    assert response.json()["error"] == "rate_limited"


@pytest.mark.anyio
async def test_cancelled_live_admission_releases_a_late_permit():
    from services.tts.tts_server import _enter_device_permit

    entered = threading.Event()
    finish_enter = threading.Event()
    released = threading.Event()

    class SlowPermit:
        def __enter__(self):
            entered.set()
            assert finish_enter.wait(2)

        def __exit__(self, *_args):
            released.set()

    task = asyncio.create_task(_enter_device_permit(SlowPermit()))
    assert await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    finish_enter.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert released.is_set()


@pytest.mark.anyio
async def test_live_tts_background_closes_stream_and_releases_unstarted_permit(monkeypatch):
    from services.tts import tts_server

    acquired = threading.Event()
    released = threading.Event()
    stream_closed = threading.Event()

    class FakePermit:
        def __enter__(self):
            acquired.set()

        def __exit__(self, *_args):
            released.set()

    class FakeStream:
        def __iter__(self):
            return iter(())

        def close(self):
            stream_closed.set()

    stream = FakeStream()

    class FakeProvider:
        sample_rate = 24_000

        def generate_audio_stream(self, **_kwargs):
            return stream

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", FakeProvider())
    monkeypatch.setattr(tts_server, "device_permit_slot", lambda *_args, **_kwargs: FakePermit())

    response = await tts_server.generate_live_call_stream(
        tts_server.TtsGenerateStreamRequest(text="hello")
    )
    assert acquired.is_set()
    assert not released.is_set()
    assert response.background is not None

    await response.background()

    assert stream_closed.is_set()
    assert released.is_set()


def test_synthesis_runs_on_the_dedicated_pool_and_health_stays_responsive():
    import httpx
    from services.tts import tts_server

    entered, release = threading.Event(), threading.Event()
    synthesis_threads: list[str] = []

    class SlowProvider:
        provider_name = "fake"

        def generate_audio(self, **_: Any):
            synthesis_threads.append(threading.current_thread().name)
            entered.set()
            release.wait(5)
            return {"success": True, "audio": ""}

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=tts_server.app),
            base_url="http://127.0.0.1",
            headers=service_headers(),
        ) as client:
            synthesis = asyncio.create_task(
                client.post("/api/tts/generate_audio", json={"text": "hi", "speaker": "default", "language": "en"})
            )
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=1)
                assert health.status_code == 200
                assert not release.is_set()
            finally:
                release.set()
            assert (await synthesis).status_code == 200

    try:
        tts_server._TTS_PROVIDER = SlowProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        asyncio.run(exercise())
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error
        release.set()

    assert synthesis_threads and synthesis_threads[0].startswith("omnix-tts-synthesis")


def test_the_gateway_voice_clone_client_and_the_tts_server_agree(monkeypatch):
    """The client uploads multipart; the server must accept exactly that (WP-7.3)."""
    import httpx
    from services.tts import tts_server

    from app import tts_http_client
    from app.runtime.http_client import HttpPolicy, PooledHttpClient

    received: dict[str, Any] = {}

    class CloningProvider:
        def voice_clone(self, voice_id, audio_data, ref_text=None):
            received.update(voice_id=voice_id, audio_data=audio_data, ref_text=ref_text)
            return {"success": True, "voice_id": voice_id}

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    server = TestClient(tts_server.app, base_url="http://127.0.0.1")

    def forward(request):  # the real client's request, served by the real server app
        served = server.request(request.method, str(request.url), headers=request.headers, content=request.content)
        return httpx.Response(served.status_code, headers=served.headers, content=served.content)

    client = PooledHttpClient("tts-test", HttpPolicy(max_retries=0), transport=httpx.MockTransport(forward))
    monkeypatch.setattr(tts_http_client, "_http", lambda: client)
    monkeypatch.setattr(tts_http_client, "_tts_base_url", lambda: "http://127.0.0.1")
    try:
        tts_server._TTS_PROVIDER = CloningProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        result = tts_http_client.tts_voice_clone(
            voice_id="narrator_2",
            ref_text="Hello there.",
            audio_bytes=b"RIFF-owned-test-audio",
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert result == {"success": True, "voice_id": "narrator_2"}
    assert received == {"voice_id": "narrator_2", "audio_data": b"RIFF-owned-test-audio", "ref_text": "Hello there."}


def test_gateway_synthesis_receives_wav_bytes_not_base64_json():
    """Accept: audio/wav keeps base64 off the wire (WP-7.3)."""
    import base64

    import httpx
    from services.tts import tts_server

    from app.providers.qwen_http_gateway import QwenHttpGatewayProvider
    from app.runtime.http_client import HttpPolicy, PooledHttpClient

    wav = b"RIFF\x24\x00\x00\x00WAVEfmt-test-bytes"
    wire: list[httpx.Response] = []

    class SynthesisProvider:
        def generate_audio(self, **_kwargs: Any):
            return {"success": True, "audio": base64.b64encode(wav).decode(), "sample_rate": 24000, "duration": 1.5}

    server = TestClient(tts_server.app, base_url="http://127.0.0.1")

    def forward(request):
        served = server.request(request.method, str(request.url), headers=request.headers, content=request.content)
        wire.append(served)
        return httpx.Response(served.status_code, headers=served.headers, content=served.content)

    gateway = QwenHttpGatewayProvider("http://127.0.0.1")
    gateway.http = PooledHttpClient("tts-test", HttpPolicy(max_retries=0), transport=httpx.MockTransport(forward))
    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = SynthesisProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        result = gateway.generate_audio("hello", speaker="Alex")
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert wire[0].headers["content-type"] == "audio/wav"
    assert wire[0].content == wav
    assert base64.b64decode(result["audio"]) == wav
    assert result["sample_rate"] == 24000
    assert result["duration"] == 1.5
