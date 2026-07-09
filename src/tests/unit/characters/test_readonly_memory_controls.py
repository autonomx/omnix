from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.assistant_memory import default_memory_service, resolve_chat_scope
from app.characters import CharacterRepository, CreateCharacterRequest
from app.chat import CreateChatSessionRequest, SendChatMessageRequest, default_chat_store
from app.gateway.main import create_gateway_app


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and easygoing.",
            default_greeting="Hey.",
        )
    )


def _seed(owner_id: str, session_id: str, content: str):
    return default_memory_service().create_explicit_memory(
        resolve_chat_scope(
            session_id,
            owner_type="character",
            owner_id=owner_id,
        ),
        scope="global",
        category="relationship",
        content=content,
        provenance_id="seed",
        pinned=True,
    )


def test_read_only_memory_commands_use_character_owner_and_reject_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(
        CreateChatSessionRequest(
            title="Maya read only",
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=False,
        )
    )
    character_record = _seed("maya", session.id, "Maya remembers the rainy hike marker.")
    system_record = default_memory_service().create_explicit_memory(
        resolve_chat_scope(session.id),
        scope="global",
        category="fact",
        content="System-only marker.",
        provenance_id="seed-system",
    )

    listed = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="what do you remember?"),
    )
    assert listed is not None
    assert "rainy hike marker" in listed[0].messages[-1].content
    assert "System-only marker" not in listed[0].messages[-1].content

    rejected = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="remember that this must not be saved"),
    )
    assert rejected is not None
    reply = rejected[0].messages[-1]
    assert "write is disabled" in reply.content
    assert reply.metadata["memory_command"]["mutated"] is False

    visible = default_memory_service().list_active(
        resolve_chat_scope(session.id, owner_type="character", owner_id="maya")
    )
    assert [record.id for record in visible] == [character_record.id]
    assert default_memory_service().repository.get_record(system_record.id) is not None


def test_write_enabled_character_command_writes_character_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(
        CreateChatSessionRequest(
            title="Maya setup",
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=True,
        )
    )

    saved = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="remember that Maya owns this setup memory"),
    )
    assert saved is not None
    result = saved[0].messages[-1].metadata["memory_command"]
    assert result["mutated"] is True
    record = default_memory_service().repository.get_record(result["memory_ids"][0])
    assert record is not None
    assert (record.owner_type, record.owner_id) == ("character", "maya")


def test_read_only_management_routes_reject_mutations_but_setup_session_can_seed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    read_only = store.create_session(
        CreateChatSessionRequest(
            title="Maya pilot",
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=False,
        )
    )
    setup = store.create_session(
        CreateChatSessionRequest(
            title="Maya setup",
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=True,
        )
    )
    client = TestClient(create_gateway_app())

    blocked = client.post(
        "/api/assistant/memory",
        json={
            "session_id": read_only.id,
            "scope": "global",
            "category": "relationship",
            "content": "This read-only write must fail.",
            "pinned": True,
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["message"] == "character_memory_write_disabled"

    seeded = client.post(
        "/api/assistant/memory",
        json={
            "session_id": setup.id,
            "scope": "global",
            "category": "relationship",
            "content": "Controlled Stage 2 setup memory.",
            "pinned": True,
        },
    )
    assert seeded.status_code == 200
    assert seeded.json()["owner_type"] == "character"
    assert seeded.json()["owner_id"] == "maya"

    record_id = seeded.json()["id"]
    blocked_delete = client.delete(
        f"/api/assistant/memory/{record_id}",
        params={"session_id": read_only.id, "expected_revision": 1},
    )
    assert blocked_delete.status_code == 403
    assert default_memory_service().repository.get_record(record_id) is not None


def test_disable_character_memory_clears_read_write_and_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    setup = default_chat_store().create_session(
        CreateChatSessionRequest(
            title="Maya setup",
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=True,
        )
    )
    _seed("maya", setup.id, "A memory used to build the read snapshot.")
    store = default_chat_store()
    session = store.create_session(
        CreateChatSessionRequest(
            title="Maya enabled",
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=False,
        )
    )
    assert session.memory_snapshot_id is not None

    disabled = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="disable memory for this chat"),
    )
    assert disabled is not None
    current = store.get_session(session.id)
    assert current is not None
    assert current.read_memory is False
    assert current.write_memory is False
    assert current.memory_snapshot_id is None
    assert current.memory_snapshot_revision is None
    assert current.memory_record_count == 0
