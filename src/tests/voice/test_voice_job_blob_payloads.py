"""Voice job rows carry blob references, never audio (WP-5.8)."""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets.models import AssetListResponse, AssetRecord, AssetType
from app.jobs.models import CreateJobRequest, ResourceClass
from app.persistence.blob_store import LocalBlobStore
from app.platform.voice import jobs as voice_jobs
from app.platform.voice.feature import voice_submission_defaults

_BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{1024,}")


def _assert_no_large_base64(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_large_base64(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_large_base64(item)
    elif isinstance(value, str):
        assert not _BASE64_RUN.search(value), "job row embeds a base64 payload over 1 KB"


@pytest.fixture
def blobs(tmp_path: Path, monkeypatch) -> LocalBlobStore:
    store = LocalBlobStore(tmp_path / "blobs")
    monkeypatch.setattr(voice_jobs, "default_blob_store", lambda: store)
    return store


def test_clone_sample_moves_to_the_blob_store_at_admission(blobs) -> None:
    audio = b"RIFF\x00\x00\x00\x00WAVE" + bytes(range(256)) * 64
    request = CreateJobRequest(
        module="voice-cloning",
        type="voice-cloning.create-profile",
        resource_class=ResourceClass.GPU_TTS,
        input_payload={
            "profile_name": "Narrator",
            "source_file_name": "narrator.wav",
            "sample_audio_base64": "data:audio/wav;base64," + base64.b64encode(audio).decode("ascii"),
        },
    )
    admitted = voice_submission_defaults(request)
    payload = admitted.input_payload or {}
    assert "sample_audio_base64" not in payload
    assert payload["sample_blob_key"].startswith("voice-samples/")
    assert payload["sample_blob_key"].endswith(".wav")
    _assert_no_large_base64(admitted.model_dump(mode="json"))
    assert voice_jobs._sample_audio_bytes(payload) == audio
    # Admission is idempotent for an already converted payload.
    assert voice_jobs.store_inline_clone_sample(dict(payload)) == payload


def test_oversized_or_empty_samples_are_refused(blobs, monkeypatch) -> None:
    monkeypatch.setattr(voice_jobs, "MAX_CLONE_SAMPLE_BYTES", 16)
    with pytest.raises(ValueError, match="too large"):
        voice_jobs.store_inline_clone_sample({"sample_audio_base64": base64.b64encode(bytes(64)).decode()})
    assert not list(Path(blobs.root).rglob("*.wav"))


@pytest.mark.parametrize("head", [b"RIFF\x00\x00\x00\x00WAVE", b"ID3\x04", b"\xff\xfb\x90", b"OggS", b"fLaC",
                                  b"\x1aE\xdf\xa3", b"\x00\x00\x00\x20ftypM4A "])
def test_audio_containers_are_accepted(blobs, head) -> None:
    sample = base64.b64encode(head + bytes(64)).decode()
    assert "sample_blob_key" in voice_jobs.store_inline_clone_sample({"sample_audio_base64": sample})


def test_a_sample_that_is_not_audio_is_refused(blobs) -> None:
    """Uploads are checked by content, not by their name (ASVS 12.2.1)."""
    for content in (b"<html><script>alert(1)</script></html>", b"MZ\x90\x00 executable", b"RIFF\x00\x00\x00\x00AVI "):
        with pytest.raises(ValueError, match="not a WAV"):
            voice_jobs.store_inline_clone_sample({"sample_audio_base64": base64.b64encode(content).decode(),
                                                  "source_file_name": "voice.wav"})
    assert not any(path.is_file() for path in Path(blobs.root).rglob("*"))


def test_rows_queued_before_the_change_still_decode() -> None:
    legacy = {"sample_audio_base64": base64.b64encode(b"legacy").decode("ascii")}
    assert voice_jobs._sample_audio_bytes(legacy) == b"legacy"


def test_speech_outputs_reference_the_stored_asset() -> None:
    assert voice_jobs.asset_audio_url("audio:voice-studio-job/1") == "/api/assets/audio%3Avoice-studio-job%2F1/audio"


class _Store:
    def __init__(self, assets: list[AssetRecord]) -> None:
        self.assets = {asset.id: asset for asset in assets}

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        return self.assets.get(asset_id)

    def list_assets(self, **_page) -> AssetListResponse:
        return AssetListResponse(assets=list(self.assets.values()))


def test_audio_route_streams_audio_assets_with_ranges(tmp_path: Path) -> None:
    from fastapi import APIRouter

    from app.composition.gateway.kernel_routes.core_assets_routes import register_core_assets_routes

    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF" + bytes(100))
    image = tmp_path / "pic.png"
    image.write_bytes(b"\x89PNG")
    store = _Store([
        AssetRecord(id="audio:1", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                    storage_path=str(audio), created_at="2026-10-01T00:00:00Z"),
        AssetRecord(id="image:1", module="image", type=AssetType.IMAGE, mime_type="image/png",
                    storage_path=str(image), created_at="2026-10-01T00:00:00Z"),
    ])
    router = APIRouter()
    register_core_assets_routes(router, get_asset_store=lambda: store)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    full = client.get("/api/assets/audio:1/audio")
    assert full.status_code == 200
    assert full.headers["content-type"] == "audio/wav"
    assert full.content == audio.read_bytes()
    ranged = client.get("/api/assets/audio:1/audio", headers={"Range": "bytes=0-3"})
    assert ranged.status_code == 206
    assert ranged.content == b"RIFF"
    assert client.get("/api/assets/image:1/audio").status_code == 415
    assert client.get("/api/assets/missing/audio").status_code == 404
