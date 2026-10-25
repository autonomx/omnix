"""A turn in a scene the campaign's bible already covers skips the scene-lore pass (F2; runtime_lore_store)."""
from __future__ import annotations

from types import SimpleNamespace

from app.apps.rpg.genesis.forge import runtime_lore_store as store

CONTEXT = SimpleNamespace(workspace_id="workspace:local")


class _Bibles:
    def __init__(self, version):
        self.version_value = version
        self.reads = 0

    def version(self, context, campaign_id):
        self.reads += 1
        return self.version_value


def _work(revision: int, content_hash: str, binding: str = "world-a"):
    return SimpleNamespace(campaign_bibles=_Bibles((revision, content_hash, binding)))


def _covered(content_hash: str, resolved: dict[str, str], binding: str = "world-a"):
    return store._Covered(4, content_hash, binding, resolved, {"entities": {}})


def test_a_covered_scene_is_skipped_only_while_the_stored_bible_and_world_are_the_same(monkeypatch) -> None:
    monkeypatch.setattr(store, "_COVERED", {})
    keys = ("loc:inn", "liora fen")
    work = _work(4, "hash-a")
    assert store._already_covered(work, CONTEXT, "c1", keys) is None  # never covered
    assert work.campaign_bibles.reads == 0  # nothing remembered: no read at all

    store._remember_covered("workspace:local", "c1", _covered("hash-a", {"loc:inn": "loc:inn"}))
    # A speaker named only by name is the canon entity the full pass resolved it to; the same bible adds up.
    store._remember_covered("workspace:local", "c1", _covered("hash-a", {"liora fen": "npc:liora_fen"}))
    covered, resolved = store._already_covered(work, CONTEXT, "c1", keys)
    assert (covered.revision, covered.content_hash, resolved) == (4, "hash-a", ("loc:inn", "npc:liora_fen"))
    assert store._already_covered(work, CONTEXT, "c1", (*keys, "npc:bran")) is None  # a newcomer
    assert store._already_covered(_work(5, "hash-b"), CONTEXT, "c1", keys) is None  # enriched since
    assert store._already_covered(_work(4, "hash-a", "world-b"), CONTEXT, "c1", keys) is None  # bound to another world
    assert store._already_covered(work, SimpleNamespace(workspace_id="workspace:other"), "c1", keys) is None

    store._remember_covered("workspace:local", "c1", _covered("hash-b", {"loc:inn": "loc:inn"}))  # a new bible
    assert store._already_covered(_work(5, "hash-b"), CONTEXT, "c1", keys) is None


def test_the_memory_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(store, "_COVERED", {})
    monkeypatch.setattr(store, "_COVERED_LIMIT", 3)
    for index in range(5):
        store._remember_covered("w", f"c{index}", _covered("h", {"x": "x"}))
    assert list(store._COVERED) == [("w", "c2"), ("w", "c3"), ("w", "c4")]
