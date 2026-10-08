from __future__ import annotations

import uuid

from pathlib import Path

from fastapi.testclient import TestClient

from app.composition.gateway.main import create_gateway_app
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
pytestmark = pytest.mark.postgres


def test_character_personality_prompt_has_no_12000_character_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Character ids are global in PostgreSQL; keep reruns independent.
    character_id = f"long-personality-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    initial_prompt = "A" * 20_000
    created = client.post(
        "/api/characters",
        json={
            "id": character_id,
            "display_name": "Long Personality",
            "personality_prompt": initial_prompt,
        },
    )
    assert created.status_code == 201
    assert created.json()["personality_prompt"] == initial_prompt

    updated_prompt = "B" * 30_000
    updated = client.patch(
        f"/api/characters/{character_id}",
        json={
            "expected_version": 1,
            "personality_prompt": updated_prompt,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["personality_prompt"] == updated_prompt
    assert updated.json()["active_version"] == 2

    reloaded = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    profile = reloaded.get(f"/api/characters/{character_id}")
    assert profile.status_code == 200
    assert profile.json()["personality_prompt"] == updated_prompt

    versions = reloaded.get(f"/api/characters/{character_id}/versions")
    assert versions.status_code == 200
    assert [item["personality_prompt"] for item in versions.json()["versions"]] == [
        updated_prompt,
        initial_prompt,
    ]
