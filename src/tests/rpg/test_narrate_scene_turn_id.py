"""Narration runs for a turn that carries its id (the in-process guard is retired)."""
from __future__ import annotations

from app.apps.rpg.ai.world_scene_narrator_runtime import narrate_scene


def test_a_turn_with_an_id_is_narrated() -> None:
    result = narrate_scene({"location": "tavern"}, {"turn_id": "turn-1"})

    assert isinstance(result, dict)
    assert "narration" in result
