from __future__ import annotations

import sqlite3

from app import shared
from app.chat import ChatMessage, ChatSession
from app.chat.history_search import SQLiteHistorySearchService
from app.chat.repository import SQLiteChatRepository
from app.chat.sqlite_store import SQLiteChatSessionStore

NOW = "2026-07-08T00:00:00+00:00"


def chat(session_id: str, project_id: str | None, content: str) -> ChatSession:
    return ChatSession(
        id=session_id,
        title=session_id,
        profile_id="profile:local",
        workspace_id="workspace:default",
        project_id=project_id,
        created_at=NOW,
        updated_at=NOW,
        message_count=2,
        messages=[
            ChatMessage(
                id=f"{session_id}:user",
                role="user",
                content=content,
                created_at=NOW,
            ),
            ChatMessage(
                id=f"{session_id}:assistant",
                role="assistant",
                content=f"Answer about {content}",
                created_at=NOW,
            ),
        ],
    )


def test_fts_search_is_scope_first_and_excludes_current_session(tmp_path):
    db = tmp_path / "chat.sqlite3"
    repository = SQLiteChatRepository(db)
    repository.save_sessions([
        chat("chat:omnix-old", "project:omnix", "Hermes memory integration details"),
        chat("chat:other", "project:other", "Hermes memory integration secret"),
        chat("chat:current", "project:omnix", "Current Hermes question"),
    ])
    service = SQLiteHistorySearchService(db)

    result = service.search(
        "Hermes memory",
        profile_id="profile:local",
        workspace_id="workspace:default",
        project_id="project:omnix",
        exclude_session_id="chat:current",
        limit=10,
    )

    assert result.status.available is True
    assert result.status.indexed_messages == 6
    assert {item.session_id for item in result.items} == {"chat:omnix-old"}
    assert all(item.session_id != "chat:current" for item in result.items)
    assert all("secret" not in item.content for item in result.items)


def test_deleted_sessions_are_removed_from_rebuilt_index(tmp_path):
    db = tmp_path / "chat.sqlite3"
    repository = SQLiteChatRepository(db)
    retained = chat("chat:retained", None, "Persistent provider preference")
    removed = chat("chat:removed", None, "Obsolete provider preference")
    repository.save_sessions([retained, removed])
    service = SQLiteHistorySearchService(db)
    assert service.search(
        "obsolete provider",
        profile_id="profile:local",
        workspace_id="workspace:default",
        project_id=None,
    ).items

    repository.save_sessions([retained])
    result = service.search(
        "obsolete provider",
        profile_id="profile:local",
        workspace_id="workspace:default",
        project_id=None,
    )

    assert result.items == []
    assert result.status.indexed_messages == 2


def test_fts_unavailability_degrades_without_raising(tmp_path):
    class Unavailable(SQLiteHistorySearchService):
        def _connect(self):
            raise sqlite3.OperationalError("no such module: fts5")

    result = Unavailable(tmp_path / "missing.sqlite3").search(
        "memory",
        profile_id="profile:local",
        workspace_id="workspace:default",
        project_id=None,
    )

    assert result.items == []
    assert result.status.available is False
    assert result.status.reason.startswith("fts5_unavailable")


def test_prompt_integration_is_feature_gated_and_separates_history_from_memory(monkeypatch, tmp_path):
    db = tmp_path / "chat.sqlite3"
    repository = SQLiteChatRepository(db)
    old = chat("chat:old", None, "The streaming bug waited for complete audio")
    current = chat("chat:current", None, "Unrelated current history")
    repository.save_sessions([old, current])
    history = SQLiteHistorySearchService(db)
    store = SQLiteChatSessionStore(
        db,
        import_legacy=False,
        history_search_factory=lambda: history,
    )
    user_message = ChatMessage(
        id="msg:new",
        role="user",
        content="What was the streaming audio bug?",
        created_at=NOW,
    )
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    disabled, disabled_rendered = store.build_provider_prompt(current, user_message, [])
    assert disabled.retrieved_history == []
    assert disabled.diagnostics["history_recall"] == {"enabled": False, "retrieved_count": 0}
    assert all("earlier conversations" not in item.content for item in disabled_rendered.messages)

    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "1")
    enabled, rendered = store.build_provider_prompt(current, user_message, [])
    text = "\n".join(item.content for item in rendered.messages)

    assert enabled.diagnostics["history_recall"]["enabled"] is True
    assert enabled.diagnostics["history_recall"]["retrieved_count"] >= 1
    assert "Relevant excerpts retrieved from earlier conversations" in text
    assert "waited for complete audio" in text
    assert "Approved remembered context follows" not in text
