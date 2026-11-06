"""A character's or the System Assistant's memory, read and edited with no chat open."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.composition.gateway.main import create_gateway_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from app.persistence.runtime import reset_persistence_mode_cache

    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))
    reset_persistence_mode_cache()
    http = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    for character_id, name in (("maya", "Maya"), ("jinx", "Jinx")):
        created = http.post("/api/characters", json={
            "id": character_id, "display_name": name, "personality_prompt": "Be yourself.", "default_greeting": "Hey.",
        })
        assert created.status_code == 201, created.text
    yield http
    reset_persistence_mode_cache()


def _add(client, owner: str, content: str = "Lives in Toronto", category: str = "fact") -> dict:
    response = client.post(f"/api/memory-owners/{owner}/records", json={"category": category, "content": content})
    assert response.status_code == 201, response.text
    return response.json()


def _view(client, owner: str) -> dict:
    response = client.get(f"/api/memory-owners/{owner}")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_memory_can_be_added_read_corrected_and_forgotten(client) -> None:
    memory = _add(client, "maya")
    assert [row["content"] for row in _view(client, "maya")["records"]] == ["Lives in Toronto"]

    edited = client.patch(f"/api/memory-owners/maya/records/{memory['id']}", json={
        "content": "Lives in Montreal", "expected_revision": memory["revision"],
    })
    assert edited.status_code == 200, edited.text
    assert edited.json()["content"] == "Lives in Montreal"
    assert [row["content"] for row in _view(client, "maya")["records"]] == ["Lives in Montreal"]

    forgotten = client.delete(
        f"/api/memory-owners/maya/records/{memory['id']}", params={"expected_revision": edited.json()["revision"]},
    )
    assert forgotten.status_code == 204, forgotten.text
    assert _view(client, "maya")["records"] == []


def test_a_stale_edit_is_refused_rather_than_overwriting(client) -> None:
    memory = _add(client, "maya")
    client.patch(f"/api/memory-owners/maya/records/{memory['id']}", json={"content": "Newer", "expected_revision": 1})

    stale = client.patch(f"/api/memory-owners/maya/records/{memory['id']}", json={"content": "Older", "expected_revision": 1})

    assert stale.status_code == 409
    assert _view(client, "maya")["records"][0]["content"] == "Newer"


def test_one_owner_cannot_see_or_change_anothers_memory(client) -> None:
    memory = _add(client, "maya")

    assert _view(client, "jinx")["records"] == []
    assert client.patch(f"/api/memory-owners/jinx/records/{memory['id']}", json={
        "content": "Taken over", "expected_revision": 1,
    }).status_code == 404
    assert client.delete(f"/api/memory-owners/jinx/records/{memory['id']}", params={"expected_revision": 1}).status_code == 404
    assert _view(client, "maya")["records"][0]["content"] == "Lives in Toronto"


def test_the_system_assistant_has_its_own_memory_through_the_same_routes(client) -> None:
    memory = _add(client, "system-assistant", "Prefers short answers", "preference")

    assert [row["id"] for row in _view(client, "system-assistant")["records"]] == [memory["id"]]
    assert memory["owner_type"] == "system"
    assert _view(client, "maya")["records"] == []


def test_an_unknown_owner_is_not_found(client) -> None:
    assert client.get("/api/memory-owners/nobody").status_code == 404
    assert client.post("/api/memory-owners/nobody/records", json={"content": "x"}).status_code == 404


def test_a_chat_with_a_character_reads_and_adds_to_its_memory_whatever_it_asks_for(client) -> None:
    created = client.post("/api/chat/sessions", json={
        "title": "With Maya", "interaction_mode": "character", "character_id": "maya",
        "read_memory": False, "write_memory": False, "shared_memory_access": "none", "transcript_policy": "persistent",
    })
    assert created.status_code in {200, 201}, created.text
    session = created.json()
    assert (session["read_memory"], session["write_memory"]) == (True, True)
    assert session["shared_memory_access"] == "none"  # one character still cannot read another's or the assistant's


def test_an_install_can_still_turn_character_memory_off(client, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "0")
    created = client.post("/api/chat/sessions", json={
        "title": "With Maya", "interaction_mode": "character", "character_id": "maya",
        "read_memory": False, "write_memory": False, "shared_memory_access": "none", "transcript_policy": "persistent",
    })
    assert created.status_code in {200, 201}, created.text
    assert (created.json()["read_memory"], created.json()["write_memory"]) == (False, False)


def test_a_new_system_assistant_chat_remembers(client) -> None:
    created = client.post("/api/chat/sessions", json={"title": "New chat", "interaction_mode": "system"})
    assert created.status_code in {200, 201}, created.text
    assert created.json()["memory_enabled"] is True
