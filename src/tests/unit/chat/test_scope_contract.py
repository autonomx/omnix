from __future__ import annotations

from app.assistant_memory import DEFAULT_PROFILE_ID, DEFAULT_WORKSPACE_ID
from app.chat import ChatSessionStore, CreateChatSessionRequest


def test_chat_session_scope_is_server_owned_and_legacy_safe(tmp_path):
    request = CreateChatSessionRequest.model_validate(
        {
            "title": "Scoped chat",
            "profile_id": "profile:forged",
            "workspace_id": "workspace:forged",
            "project_id": "project:forged",
            "memory_enabled": True,
        }
    )
    store = ChatSessionStore(tmp_path / "chat.json")

    session = store.create_session(request)

    assert session.profile_id == DEFAULT_PROFILE_ID
    assert session.workspace_id == DEFAULT_WORKSPACE_ID
    assert session.project_id is None
    assert session.memory_enabled is False
    assert session.memory_snapshot_id is None
    assert session.memory_record_count == 0


def test_legacy_chat_payload_receives_memory_scope_defaults():
    from app.chat import ChatSession

    session = ChatSession.model_validate(
        {
            "id": "chat:legacy",
            "title": "Legacy",
            "message_count": 0,
            "created_at": "2026-07-08T00:00:00+00:00",
            "updated_at": "2026-07-08T00:00:00+00:00",
            "messages": [],
        }
    )

    assert session.profile_id == DEFAULT_PROFILE_ID
    assert session.workspace_id == DEFAULT_WORKSPACE_ID
    assert session.project_id is None
    assert session.memory_enabled is False
    assert session.memory_snapshot_revision is None
