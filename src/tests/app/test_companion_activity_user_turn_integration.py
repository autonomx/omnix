from __future__ import annotations

from pathlib import Path

from app.characters import CharacterRepository, CreateCharacterRequest
from app.chat import (
    CreateChatSessionRequest,
    SendChatMessageRequest,
    default_chat_store,
)
from app.desktop_companion import chat_activity
from app.gateway import companion_activity_user_turn as user_turn_hook


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be easygoing and warm.",
            default_greeting="Hey, good to hear from you.",
        )
    )


def test_accepted_character_chat_turn_reaches_companion_activity_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    calls: list[tuple[str, str | None, str, str]] = []

    def record(session, user_message):
        calls.append(
            (
                session.id,
                session.character_id,
                user_message.id,
                user_message.content,
            )
        )

    monkeypatch.setattr(user_turn_hook, "record_accepted_chat_activity", record)
    user_turn_hook.install_companion_activity_user_turn_hook()

    store = default_chat_store()
    session = store.create_session(
        CreateChatSessionRequest(
            title="Companion activity",
            interaction_mode="character",
            character_id="maya",
        )
    )
    begun = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="I'm trying to beat the Iron Sentinel.",
            user_turn_id="activity-user-turn:1",
        ),
    )

    assert begun is not None
    persisted_session, user_message = begun
    assert persisted_session.messages[-1].id == user_message.id
    assert calls == [
        (
            session.id,
            "maya",
            user_message.id,
            "I'm trying to beat the Iron Sentinel.",
        )
    ]


def test_activity_enrichment_failure_does_not_reject_chat_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)

    class FailingBridge:
        def record_user_turn(self, **_kwargs):
            raise RuntimeError("activity unavailable")

    monkeypatch.setattr(
        chat_activity,
        "default_desktop_companion_activity_bridge",
        lambda: FailingBridge(),
    )
    monkeypatch.setattr(
        user_turn_hook,
        "record_accepted_chat_activity",
        chat_activity.record_accepted_chat_activity,
    )
    user_turn_hook.install_companion_activity_user_turn_hook()

    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Companion degraded"))
    begun = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="Ordinary chat turn"),
    )

    assert begun is not None
    persisted_session, user_message = begun
    assert persisted_session.messages[-1].id == user_message.id
    assert persisted_session.messages[-1].content == "Ordinary chat turn"
