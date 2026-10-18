from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from app.platform.characters.live_conversation_profile import LiveConversationProfileStore
from app.platform.characters.models import UpdateCharacterRequest
from app.platform.characters.service import CharacterService
from app.platform.live_voice.prompt import cache as prompt_cache


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
    prompt_cache.cache_character_snapshot(snapshot)
    resolution_calls: list[object] = []

    def fake_resolve(selection: object, *, character: object) -> _FakeIdentity:
        resolution_calls.append((selection, character))
        return _FakeIdentity(marker="resolved")

    class FailingService:
        def resolve_snapshot(self, character_id: str) -> object:
            raise AssertionError(f"unexpected character reload: {character_id}")

    monkeypatch.setattr(prompt_cache, "resolve_interaction_context", fake_resolve)
    monkeypatch.setattr(prompt_cache, "default_character_service", lambda: FailingService())

    first = prompt_cache.resolve_system_session_identity_cached(_character_session())
    second = prompt_cache.resolve_system_session_identity_cached(_character_session())

    assert first.marker == "resolved"
    assert second.marker == "resolved"
    assert first is not second
    assert len(resolution_calls) == 1


def test_character_service_snapshot_events_seed_and_invalidate_prompt_cache() -> None:
    prompt_cache._reset_live_prompt_cache_for_tests()
    snapshot = SimpleNamespace(id="sofia", version=7)

    class Repository:
        def get(self, character_id, *, include_archived=False):
            del character_id, include_archived
            return SimpleNamespace(snapshot=lambda: snapshot)

        def update(self, character_id, request):
            del request
            return SimpleNamespace(id=character_id)

    service = CharacterService(repository=Repository())
    service.resolve_snapshot("sofia")
    assert ("sofia", 7) in prompt_cache._CHARACTER_SNAPSHOTS

    service.update("sofia", UpdateCharacterRequest(expected_version=7))
    assert ("sofia", 7) not in prompt_cache._CHARACTER_SNAPSHOTS


def test_profile_cache_uses_file_signature_and_observes_updates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    prompt_cache._reset_live_prompt_cache_for_tests()
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

    first = prompt_cache.get_live_conversation_profile_cached(store, "chat:test")
    second = prompt_cache.get_live_conversation_profile_cached(store, "chat:test")

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
    # The rewrite has the same size, and a coarse filesystem clock (Linux updates mtimes per tick) can give it the
    # same mtime: date it a second later, as an edit made later would be.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    updated = prompt_cache.get_live_conversation_profile_cached(store, "chat:test")

    assert updated.effective.talkativeness == 20
    assert updated.effective.profile_version == 2
    assert read_calls == 2


def test_prompt_dependency_cache_expires_and_supports_invalidation(monkeypatch) -> None:
    now = [5.0]
    cache: OrderedDict[str, object] = OrderedDict()
    monkeypatch.setattr(prompt_cache, "_cache_now", lambda: now[0])

    prompt_cache._bounded_put(cache, "identity", {"value": 1})
    assert prompt_cache._cache_get(cache, "identity") == {"value": 1}

    now[0] += prompt_cache._CACHE_TTL_SECONDS + 1
    assert prompt_cache._cache_get(cache, "identity") is None

    prompt_cache._bounded_put(cache, "identity", {"value": 2})
    prompt_cache.clear_live_prompt_caches()
    snapshot = SimpleNamespace(id="sofia", version=99)
    prompt_cache.cache_character_snapshot(snapshot)
    assert ("sofia", 99) in prompt_cache._CHARACTER_SNAPSHOTS
    prompt_cache.clear_live_prompt_caches()
    assert ("sofia", 99) not in prompt_cache._CHARACTER_SNAPSHOTS
