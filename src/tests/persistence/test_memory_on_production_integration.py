"""Memory switched on, through the production app and PostgreSQL: the path a real install runs.

The rest of these tests use in-memory stores or single services, which is how a character's second chat came to fail
only on a real install. So this drives the app's own routes and job handler.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.xdist_group("memory_on_production"),
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def app_client(monkeypatch):
    from app.composition.production import create_production_app
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase, close_default_database
    from app.persistence.identity_service import ensure_local_identity
    from app.persistence.migrations import apply_migrations
    from app.persistence.runtime import reset_persistence_mode_cache
    from app.runtime.config import GatewayRole, RuntimeConfig

    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    monkeypatch.setenv("OMNIX_DATABASE_URL", url)
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "postgresql")
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE", "deterministic")
    reset_persistence_mode_cache()
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    apply_migrations(database)
    ensure_local_identity(database)
    database.close()
    app = create_production_app(RuntimeConfig(gateway_role=GatewayRole.API))
    try:
        with TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"}) as client:
            yield client, app
    finally:
        close_default_database()
        reset_persistence_mode_cache()


def _character(client: TestClient) -> str:
    character_id = f"memory-test-{uuid.uuid4().hex[:10]}"
    created = client.post("/api/characters", json={
        "id": character_id, "display_name": "Test", "personality_prompt": "Be yourself.", "default_greeting": "Hey.",
    })
    assert created.status_code == 201, created.text
    return character_id


def _chat(client: TestClient, character_id: str) -> dict:
    created = client.post("/api/chat/sessions", json={
        "title": "With a character", "interaction_mode": "character", "character_id": character_id,
        "read_memory": False, "write_memory": False, "shared_memory_access": "none", "transcript_policy": "persistent",
    })
    assert created.status_code in {200, 201}, created.text
    return created.json()


def test_a_character_can_have_many_chats_once_memory_is_on(app_client) -> None:
    # Real: the second chat with a character failed on a unique snapshot revision.
    client, _app = app_client
    character_id = _character(client)

    chats = [_chat(client, character_id) for _ in range(3)]

    assert len({chat["id"] for chat in chats}) == 3
    assert all((chat["read_memory"], chat["write_memory"]) == (True, True) for chat in chats)


def test_a_chat_can_switch_to_a_character_that_already_has_chats(app_client) -> None:
    client, _app = app_client
    character_id = _character(client)
    _chat(client, character_id)
    other = client.post("/api/chat/sessions", json={"title": "New chat", "interaction_mode": "system"})
    assert other.status_code in {200, 201}, other.text

    switched = client.post(f"/api/chat/sessions/{other.json()['id']}/interaction", json={
        "interaction_mode": "character", "character_id": character_id,
        "read_memory": False, "write_memory": False, "shared_memory_access": "none", "transcript_policy": "persistent",
    })

    assert switched.status_code == 200, switched.text
    assert switched.json()["read_memory"] is True


def test_refreshing_a_chats_memory_counts_within_that_chat(app_client) -> None:
    client, _app = app_client
    character_id = _character(client)
    first, second = _chat(client, character_id), _chat(client, character_id)

    for chat in (first, second):
        state = client.get(f"/api/chat/sessions/{chat['id']}/memory").json()
        refreshed = client.post(f"/api/chat/sessions/{chat['id']}/memory/refresh", json={
            "token_budget": 4000, "expected_snapshot_revision": state["snapshot_revision"],
        })
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["snapshot_revision"] == state["snapshot_revision"] + 1


def test_the_memory_tab_works_on_the_real_store(app_client) -> None:
    client, _app = app_client
    character_id = _character(client)

    added = client.post(f"/api/memory-owners/{character_id}/records", json={"category": "preference", "content": "Likes chocolate"})
    assert added.status_code == 201, added.text
    memory = added.json()
    assert [row["content"] for row in client.get(f"/api/memory-owners/{character_id}").json()["records"]] == ["Likes chocolate"]

    edited = client.patch(f"/api/memory-owners/{character_id}/records/{memory['id']}", json={
        "content": "Likes dark chocolate", "expected_revision": memory["revision"],
    })
    assert edited.status_code == 200, edited.text
    assert client.get(f"/api/memory-owners/{character_id}").json()["records"][0]["content"] == "Likes dark chocolate"

    # A chat with the character sees it: this is what makes it remember across chats.
    chat = _chat(client, character_id)
    state = client.get(f"/api/chat/sessions/{chat['id']}/memory")
    assert state.status_code == 200, state.text

    forgotten = client.delete(
        f"/api/memory-owners/{character_id}/records/{memory['id']}", params={"expected_revision": edited.json()["revision"]},
    )
    assert forgotten.status_code == 204, forgotten.text
    assert client.get(f"/api/memory-owners/{character_id}").json()["records"] == []


def test_the_system_assistant_memory_tab_works_on_the_real_store(app_client) -> None:
    client, _app = app_client
    content = f"Prefers short answers {uuid.uuid4().hex[:6]}"
    added = client.post("/api/memory-owners/system-assistant/records", json={"category": "preference", "content": content})
    assert added.status_code == 201, added.text
    memory = added.json()

    assert content in [row["content"] for row in client.get("/api/memory-owners/system-assistant").json()["records"]]

    forgotten = client.delete(
        f"/api/memory-owners/system-assistant/records/{memory['id']}", params={"expected_revision": memory["revision"]},
    )
    assert forgotten.status_code == 204, forgotten.text
