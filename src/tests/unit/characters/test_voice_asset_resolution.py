"""Finding a character's voice without listing every asset: a live call's runtime asks three times."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.characters import service as character_service
from app.platform.characters.service import CharacterService


def _asset(asset_id: str, source: str) -> SimpleNamespace:
    return SimpleNamespace(id=asset_id, source=source)


class CountingStore:
    """An asset store that records how it was read."""

    def __init__(self, *asset_ids: str) -> None:
        self.assets = {asset_id: _asset(asset_id, "store") for asset_id in asset_ids}
        self.lists = 0
        self.reads = 0

    def get_asset(self, asset_id: str) -> SimpleNamespace | None:
        self.reads += 1
        return self.assets.get(asset_id)

    def list_assets(self, **_kwargs: object) -> SimpleNamespace:
        self.lists += 1
        return SimpleNamespace(assets=list(self.assets.values()), has_more=False, next_cursor=None)


@pytest.fixture
def resolve(monkeypatch):
    def build(store: CountingStore, *canonical: str):
        monkeypatch.setattr(character_service, "discover_canonical_voice_clone_assets",
                            lambda: [_asset(asset_id, "canonical") for asset_id in canonical])
        return CharacterService(repository=object(), asset_store_factory=lambda: store).resolve_voice_asset
    return build


def test_an_exact_id_in_the_store_does_not_list_every_asset(resolve) -> None:
    store = CountingStore("voice-cloning:maya", "image:one", "image:two")
    assert resolve(store)("voice-cloning:maya").id == "voice-cloning:maya"
    assert (store.reads, store.lists) == (1, 0)


def test_a_voice_only_in_the_clone_folder_does_not_list_every_asset(resolve) -> None:
    # The usual case for a cloned voice: the library reads the folder, and the store has never imported it.
    store = CountingStore("image:one", "image:two")
    assert resolve(store, "voice-cloning:Ehsan")("voice-cloning:Ehsan").source == "canonical"
    assert store.lists == 0


def test_the_store_wins_when_both_have_the_voice(resolve) -> None:
    store = CountingStore("voice-cloning:maya")
    assert resolve(store, "voice-cloning:maya")("voice-cloning:maya").source == "store"


def test_an_older_profiles_casing_is_still_repaired(resolve) -> None:
    store = CountingStore("image:one")
    assert resolve(store, "voice-cloning:jinx")("voice-cloning:Jinx").id == "voice-cloning:jinx"
    assert store.lists == 1  # only now is everything listed


def test_an_ambiguous_casing_and_an_unknown_voice_find_nothing(resolve) -> None:
    store = CountingStore("voice-cloning:JINX")
    assert resolve(store, "voice-cloning:jinx")("voice-cloning:Jinx") is None
    assert resolve(store)("voice-cloning:nobody") is None
    assert resolve(store)("  ") is None


def test_a_store_that_fails_still_finds_a_voice_in_the_clone_folder(resolve) -> None:
    class BrokenStore(CountingStore):
        def get_asset(self, asset_id: str) -> None:
            raise OSError("store unavailable")

        def list_assets(self, **_kwargs: object) -> SimpleNamespace:
            raise OSError("store unavailable")

    resolver = resolve(BrokenStore(), "voice-cloning:maya")
    assert resolver("voice-cloning:maya").source == "canonical"
    assert resolver("voice-cloning:MAYA").id == "voice-cloning:maya"
