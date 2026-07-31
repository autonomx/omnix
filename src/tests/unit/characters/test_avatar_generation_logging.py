from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.characters.avatar_generation_api import register_character_avatar_generation_routes


class _FailingAvatarGenerationService:
    def create(self, character_id, request):
        raise RuntimeError(f"image queue unavailable for {character_id}")


def test_avatar_generation_500_writes_traceback_to_resources_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "resources" / "logs" / "avatar_generation.log"
    monkeypatch.setenv("OMNIX_AVATAR_GENERATION_LOG_PATH", str(log_path))

    app = FastAPI()
    register_character_avatar_generation_routes(
        app,
        service_factory=lambda: _FailingAvatarGenerationService(),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/characters/anaka/avatar-generations", json={})

    assert response.status_code == 500
    contents = log_path.read_text(encoding="utf-8")
    assert "event=avatar_generation_request_started" in contents
    assert "event=avatar_generation_request_failed" in contents
    assert '"character_id": "anaka"' in contents
    assert "RuntimeError: image queue unavailable for anaka" in contents
