from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.assets.canonical_voice_clones as canonical_voice_clones
from tests.support.routers import include_router_registrar
from app.platform.voice.voice_library_routes import register_voice_library_route


def test_direct_voice_library_route_reads_canonical_clone_folder(tmp_path, monkeypatch) -> None:
    resources = tmp_path / "resources"
    clone_dir = resources / "voice_clones"
    clone_dir.mkdir(parents=True)
    maya_path = clone_dir / "Maya.wav"
    maya_path.write_bytes(b"voice-audio")

    monkeypatch.setattr(canonical_voice_clones, "resources_root", lambda: resources)

    gateway = FastAPI()
    include_router_registrar(gateway, register_voice_library_route)
    response = TestClient(gateway).get("/api/voice-library")

    assert response.status_code == 200
    assert response.headers["x-omnix-voice-profile-count"] == "1"
    assert response.headers["x-omnix-voice-library-source"] == "resources/voice_clones"
    payload = response.json()
    assert len(payload["assets"]) == 1
    assert payload["assets"][0]["id"] == "voice-cloning:Maya"
    assert payload["assets"][0]["type"] == "voice_profile"
    assert payload["assets"][0]["file_name"] == "Maya.wav"
    assert payload["assets"][0]["download_url"] == "/api/assets/voice-cloning%3AMaya/download"
    # Where the clone is stored never reaches the client (WP-4.10).
    assert "storage_path" not in payload["assets"][0]
    assert str(clone_dir) not in response.text and str(clone_dir).replace("\\", "\\\\") not in response.text
