from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from app.characters.live_conversation_profile import LiveConversationProfileStore
from app.gateway import live_chat_prompt_cache as prompt_cache


class _FakeIdentity(BaseModel):
    marker: str


def _character_session() -> SimpleNamespace:
    return SimpleNamespace(
        interaction_mode="character",
        character_id="sofia",
        character_profile_version=7,
        effective_identity_hash="a" * 64,
        voice_asset_id="voice-cloning:Sofia",
        read_memory=False,
        write_memory=False,
        shared_memory_access="none",
        transcript_policy="persistent",
    )


def test_reuses_character_snapshot_preloaded_by_live_call(monkeypatch) -> None:
    prompt_cache._reset_live_prompt_cache_for_tests()
    snapshot = SimpleNamespace(id="sofia", version=7)
    prompt_cache._cache_character_snapshot(snapshot)
    resolution_calls: list[object] = []

    def fake_resolve(selection: object, *, character: object) -> _FakeIdentity:
        resolution_calls.append((selection, character))
        return _FakeIdentity(marker="resolved")

    class FailingService:
        def resolve_snapshot(self, character_id: str) -> object:
            raise AssertionError(f"unexpected character reload: {character_id}")

    monkeypatch.setattr(prompt_cache, "resolve_interaction_context", fake_resolve)
    monkeypatch.setattr(prompt_cache, "default_character_service", lambda: FailingService())

    first = prompt_cache._resolve_system_session_identity_cached(_character_session())
    second = prompt_cache._resolve_system_session_identity_cached(_character_session())

    assert first.marker == "resolved"
    assert second.marker == "resolved"
    assert first is not second
    assert len(resolution_calls) == 1


def test_profile_cache_uses_file_signature_and_observes_updates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    prompt_cache._reset_live_prompt_cache_for_tests()
    prompt_cache.install_live_chat_prompt_cache_hook()
    path = tmp_path / "live-conversation-profiles.json"
    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "defaults": {"talkativeness": 10, "profile_version": 1},
                "sessions": {},
            }
        ),
        encoding="utf-8",
    )
    store = LiveConversationProfileStore(path)
    original_read_text = Path.read_text
    read_calls = 0

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        read_calls += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    first = store.get("chat:test")
    second = store.get("chat:test")

    assert first.effective.talkativeness == 10
    assert second.effective.talkativeness == 10
    assert read_calls == 1

    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "defaults": {"talkativeness": 20, "profile_version": 2},
                "sessions": {},
            }
        ),
        encoding="utf-8",
    )
    updated = store.get("chat:test")

    assert updated.effective.talkativeness == 20
    assert updated.effective.profile_version == 2
    assert read_calls == 2
