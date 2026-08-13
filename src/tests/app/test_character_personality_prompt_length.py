from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def test_character_personality_prompt_has_no_12000_character_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app())

    initial_prompt = "A" * 20_000
    created = client.post(
        "/api/characters",
        json={
            "id": "long-personality",
            "display_name": "Long Personality",
            "personality_prompt": initial_prompt,
        },
    )
    assert created.status_code == 201
    assert created.json()["personality_prompt"] == initial_prompt

    updated_prompt = "B" * 30_000
    updated = client.patch(
        "/api/characters/long-personality",
        json={
            "expected_version": 1,
            "personality_prompt": updated_prompt,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["personality_prompt"] == updated_prompt
    assert updated.json()["active_version"] == 2

    reloaded = TestClient(create_gateway_app())
    profile = reloaded.get("/api/characters/long-personality")
    assert profile.status_code == 200
    assert profile.json()["personality_prompt"] == updated_prompt

    versions = reloaded.get("/api/characters/long-personality/versions")
    assert versions.status_code == 200
    assert [item["personality_prompt"] for item in versions.json()["versions"]] == [
        updated_prompt,
        initial_prompt,
    ]
