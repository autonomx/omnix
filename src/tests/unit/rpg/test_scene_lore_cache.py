"""The scene's lore evidence is built once for a scene at a canon (evolution roadmap EV-7): kept by both bible
snapshots' content hashes, the scene's entries, the place and the time of day."""
from __future__ import annotations

from types import SimpleNamespace

from app.apps.rpg.genesis.forge import turn_grounding


def test_a_scene_at_one_canon_builds_its_lore_once(monkeypatch) -> None:
    built: list[tuple] = []

    def select(loaded, portable, targets):
        built.append((loaded.content_hash, tuple(targets)))
        return (loaded, ("record",), ())

    monkeypatch.setattr(turn_grounding, "select_complete_turn_snapshot", select)
    monkeypatch.setattr(turn_grounding, "_SCENE_LORE", turn_grounding.OrderedDict())
    session = {"simulation_state": {"player_state": {"location_id": "loc:a"}, "environment": {"absolute_minutes": 600}}}
    canon = SimpleNamespace(content_hash="hash:1")
    assert turn_grounding._scene_lore(session, canon, None, ("npc:a",))[1] == ("record",)
    turn_grounding._scene_lore(session, canon, None, ("npc:a",))
    assert built == [("hash:1", ("npc:a",))]  # the second turn in the scene reads it
    turn_grounding._scene_lore(session, SimpleNamespace(content_hash="hash:2"), None, ("npc:a",))  # the canon moved
    night = {"simulation_state": {**session["simulation_state"], "environment": {"absolute_minutes": 22 * 60}}}
    turn_grounding._scene_lore(night, canon, None, ("npc:a",))  # another time of day
    assert len(built) == 3
