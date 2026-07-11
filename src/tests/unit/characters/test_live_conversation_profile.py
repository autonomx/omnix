from __future__ import annotations

from pathlib import Path

from app.characters.live_conversation_profile import (
    LiveConversationProfileStore,
    LiveConversationProfileUpdate,
)


def test_live_conversation_profile_defaults_and_session_override(tmp_path: Path) -> None:
    path = tmp_path / "live-conversation.json"
    store = LiveConversationProfileStore(path)

    defaults = store.get_defaults()
    assert defaults.presence_preset == "natural"
    assert defaults.profile_version == 1

    updated_defaults = store.update_defaults(
        LiveConversationProfileUpdate(
            presence_preset="engaged",
            talkativeness=75,
            conversation_pace="reflective",
        )
    )
    assert updated_defaults.profile_version == 2
    assert updated_defaults.presence_preset == "engaged"

    inherited = store.get("chat:one")
    assert inherited.source == "user_defaults"
    assert inherited.session_override is None
    assert inherited.effective.talkativeness == 75

    overridden = store.update(
        "chat:one",
        LiveConversationProfileUpdate(conversation_stance="listen"),
    )
    assert overridden.source == "session_override"
    assert overridden.effective.conversation_stance == "listen"
    assert overridden.effective.presence_preset == "engaged"
    assert overridden.effective.profile_version == 3

    reloaded = LiveConversationProfileStore(path).get("chat:one")
    assert reloaded.effective == overridden.effective
    assert path.is_file()
    assert not path.with_suffix(".json.tmp").exists()

    cleared = store.clear("chat:one")
    assert cleared.source == "user_defaults"
    assert cleared.session_override is None
    assert cleared.effective == updated_defaults


def test_live_conversation_profile_recovers_from_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "live-conversation.json"
    path.write_text("not-json", encoding="utf-8")

    profile = LiveConversationProfileStore(path).get_defaults()

    assert profile.presence_preset == "natural"
    assert profile.talkativeness == 50
