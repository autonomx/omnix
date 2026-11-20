from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.characters.live_conversation_profile import (
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


def test_scene_talk_settings_are_global_and_read_from_the_defaults(tmp_path: Path) -> None:
    store = LiveConversationProfileStore(tmp_path / "live-conversation.json")
    store.update("chat:one", LiveConversationProfileUpdate(conversation_stance="listen"))
    store.update_defaults(LiveConversationProfileUpdate(
        scene_talk_enabled=True, scene_talk_level="often", scene_talk_max_lines=6, scene_memory_per_character=3,
    ))

    envelope = store.get("chat:one")
    effective = envelope.effective
    assert envelope.source == "session_override"
    assert effective.conversation_stance == "listen"
    assert (effective.scene_talk_enabled, effective.scene_talk_level) == (True, "often")
    assert (effective.scene_talk_max_lines, effective.scene_memory_per_character) == (6, 3)
    assert effective.scene_talk_silence_seconds() == 20.0
    assert effective.scene_talk_attempt_cap() == 24

    # A chat's own update cannot switch talk off for that chat.
    after = store.update("chat:one", LiveConversationProfileUpdate(scene_talk_enabled=False, talkativeness=10))
    assert after.effective.scene_talk_enabled is True
    assert after.effective.talkativeness == 10


def test_characters_talk_by_default_and_an_exchange_runs_to_ten_lines(tmp_path: Path) -> None:
    # Owner 2026-11-19: group calls are lively by default; up to ten lines in one exchange, six unless set.
    store = LiveConversationProfileStore(tmp_path / "live-conversation.json")
    defaults = store.get_defaults()
    assert (defaults.scene_talk_enabled, defaults.scene_talk_max_lines) == (True, 6)
    assert store.update_defaults(LiveConversationProfileUpdate(scene_talk_max_lines=10)).scene_talk_max_lines == 10
    with pytest.raises(ValidationError):
        LiveConversationProfileUpdate(scene_talk_max_lines=11)


def test_scene_talk_attempts_per_hour_null_means_the_level(tmp_path: Path) -> None:
    store = LiveConversationProfileStore(tmp_path / "live-conversation.json")
    assert store.update_defaults(LiveConversationProfileUpdate(scene_talk_attempts_per_hour=48)).scene_talk_attempt_cap() == 48
    kept = store.update_defaults(LiveConversationProfileUpdate(talkativeness=20))
    assert kept.scene_talk_attempts_per_hour == 48
    cleared = store.update_defaults(LiveConversationProfileUpdate.model_validate({"scene_talk_attempts_per_hour": None}))
    assert cleared.scene_talk_attempts_per_hour is None
    assert cleared.scene_talk_attempt_cap() == 12
