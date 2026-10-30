"""Setting up a portrait: the preview route and forgetting released portraits (live portrait roadmap, Phase 4)."""
from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.platform.live_voice.portrait import cleanup
from app.platform.live_voice.portrait.cleanup import PortraitCacheCleaner
from app.platform.live_voice.portrait.link import PortraitUnavailable
from app.platform.live_voice.transport import portrait_preview


class SpeakingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        yield [0.1] * 2_400, 24_000, {}
        yield [0.1] * 2_400, 24_000, {}


def _client(monkeypatch, provider: Any, outcome: Any) -> TestClient:
    async def prepare(base_url: str, tenant: str, image: bytes) -> str:
        if isinstance(outcome, PortraitUnavailable):
            raise outcome
        assert image == b"portrait bytes"
        return "latent-key"

    async def preview(base_url: str, latent_key: str, emotion: str, pcm: bytes, rate: int) -> list[str]:
        assert (latent_key, emotion, rate, len(pcm)) == ("latent-key", "happy", 24_000, 9_600)
        return [base64.b64encode(b"jpeg").decode()]

    monkeypatch.setattr(portrait_preview, "portrait_url", lambda: "http://portrait.test")
    monkeypatch.setattr(portrait_preview, "_read_image", lambda asset_id: b"portrait bytes")
    monkeypatch.setattr(portrait_preview, "prepare_portrait", prepare)
    monkeypatch.setattr(portrait_preview, "preview_portrait", preview)
    router = APIRouter()
    portrait_preview.register_portrait_preview_route(router, provider_factory=lambda: provider)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_preview_speaks_the_sample_line_in_the_calls_voice_and_returns_audio_and_frames(monkeypatch) -> None:
    provider = SpeakingProvider()
    body = _client(monkeypatch, provider, None).post(
        "/api/tts/live-call/portrait-preview", json={"asset_id": "image:maya", "emotion": "happy",
                                                     "speaker": "voice:maya"}).json()
    assert body["ok"] and body["sample_rate"] == 24_000 and body["fps"] == 25
    assert len(base64.b64decode(body["audio"])) == 9_600 and body["frames"] == [base64.b64encode(b"jpeg").decode()]
    assert provider.calls[0]["speaker"] == "voice:maya" and provider.calls[0]["text"] == portrait_preview.SAMPLE_LINE


def test_a_refused_portrait_says_why(monkeypatch) -> None:
    body = _client(monkeypatch, SpeakingProvider(), PortraitUnavailable("no_face", "No face was found")).post(
        "/api/tts/live-call/portrait-preview", json={"asset_id": "image:maya"}).json()
    assert body == {**body, "ok": False, "code": "no_face", "message": "No face was found"}


def test_without_a_portrait_service_the_preview_says_so(monkeypatch) -> None:
    client = _client(monkeypatch, SpeakingProvider(), None)
    monkeypatch.setattr(portrait_preview, "portrait_url", lambda: "")
    assert client.post("/api/tts/live-call/portrait-preview",
                       json={"asset_id": "image:maya"}).json()["code"] == "portrait_not_configured"


def test_a_released_portrait_is_forgotten_by_its_tenant_and_image_digest(monkeypatch) -> None:
    forgotten: list[tuple[str, str, str]] = []
    monkeypatch.setattr(cleanup, "portrait_url", lambda: "http://portrait.test")
    store = SimpleNamespace(read_asset_bytes=lambda asset_id, max_bytes: b"portrait bytes")
    cleaner = PortraitCacheCleaner(asset_store_factory=lambda: store,
                                   forget=lambda *args: forgotten.append(args), background=False)
    cleaner.on_portrait_released("image:maya")
    from app.runtime.tenant_context import current_tenant

    assert forgotten == [("http://portrait.test", current_tenant().workspace_id,
                          hashlib.sha256(b"portrait bytes").hexdigest())]
    monkeypatch.setattr(cleanup, "portrait_url", lambda: "")
    cleaner.on_portrait_released("image:maya")
    assert len(forgotten) == 1
