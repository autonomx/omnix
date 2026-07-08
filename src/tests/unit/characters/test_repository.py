from __future__ import annotations

from pathlib import Path

import pytest

from app.characters import (
    CharacterConflictError,
    CharacterRepository,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)


def _create_request(**overrides: object) -> CreateCharacterRequest:
    payload: dict[str, object] = {
        "display_name": "Maya",
        "description": "An easygoing AI character.",
        "personality_prompt": "Be warm, easygoing, and lightly humorous.",
        "default_greeting": "Hey, good to hear from you.",
        "speech_style": {"speed": 0.94, "expressiveness": "relaxed"},
    }
    payload.update(overrides)
    return CreateCharacterRequest(**payload)


def test_repository_persists_profile_and_version_history(tmp_path: Path) -> None:
    db_path = tmp_path / "characters.sqlite3"
    repository = CharacterRepository(db_path)

    created = repository.create(_create_request())
    updated = repository.update(
        created.id,
        UpdateCharacterRequest(
            expected_version=1,
            personality_prompt="Be calm, warm, curious, and lightly humorous.",
            enabled=False,
        ),
    )

    restarted = CharacterRepository(db_path)
    loaded = restarted.get(created.id)
    versions = restarted.versions(created.id)

    assert loaded == updated
    assert loaded is not None
    assert loaded.active_version == 2
    assert loaded.enabled is False
    assert [item.version for item in versions] == [2, 1]
    assert versions[0].personality_prompt.startswith("Be calm")
    assert versions[1].personality_prompt.startswith("Be warm")


def test_repository_rejects_stale_profile_update(tmp_path: Path) -> None:
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    created = repository.create(_create_request())
    repository.update(
        created.id,
        UpdateCharacterRequest(expected_version=1, description="Updated"),
    )

    with pytest.raises(CharacterConflictError, match="version conflict"):
        repository.update(
            created.id,
            UpdateCharacterRequest(expected_version=1, description="Stale"),
        )


def test_archive_keeps_versions_and_hides_profile_by_default(tmp_path: Path) -> None:
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    created = repository.create(_create_request())

    archived = repository.archive(created.id)

    assert archived.status == "archived"
    assert archived.enabled is False
    assert repository.get(created.id) is None
    assert repository.get(created.id, include_archived=True) == archived
    assert len(repository.versions(created.id)) == 1


def test_voice_can_be_explicitly_cleared(tmp_path: Path) -> None:
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    created = repository.create(
        _create_request(default_voice_asset_id="voice-cloning:maya")
    )

    updated = repository.update(
        created.id,
        UpdateCharacterRequest(expected_version=1, clear_default_voice=True),
    )

    assert updated.default_voice_asset_id is None
    assert updated.active_version == 2


def test_repository_persists_identity_segments(tmp_path: Path) -> None:
    repository = CharacterRepository(tmp_path / "characters.sqlite3")
    created = repository.create(_create_request())
    segment = repository.create_segment(
        session_id="chat:one",
        interaction_mode="character",
        character_id=created.id,
        profile_version=created.active_version,
        transcript_policy="persistent",
        read_memory=False,
        write_memory=False,
        shared_memory_access="none",
    )

    closed = repository.close_segment(segment.id)
    loaded = CharacterRepository(tmp_path / "characters.sqlite3").segments("chat:one")

    assert closed is not None
    assert closed.ended_at is not None
    assert loaded == [closed]
