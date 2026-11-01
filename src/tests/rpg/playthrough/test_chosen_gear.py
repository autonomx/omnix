"""Playthrough: the gear a player chooses is theirs on a published world.

The new game keeps the chosen kit in its metadata, but the published launch looked for it on the hero's sheet, so it
never found it: the opening's kit replaced it, and a world to come reskinned it besides (the M2 dev split, 2026-10-31:
a hero who chose an Iron Dagger on Vesper-9 carried a Utility Knife).
"""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES, Playthrough, launch_vesper

pytestmark = POSTGRES


def test_a_chosen_kit_is_carried_as_chosen_on_a_world_to_come(tmp_path, monkeypatch) -> None:
    session_id, _ = launch_vesper(tmp_path, monkeypatch, new_game={
        "generated_class_summary": "Starter gear: Iron Dagger, Travel Cloak, 10 silver"})
    items = Playthrough(session_id).simulation()["player_state"]["inventory_state"]["items"]
    names = {str(row.get("name")) for row in items}
    assert {"Iron Dagger", "Travel Cloak"} <= names and "Utility Knife" not in names, names


def test_with_no_kit_chosen_a_world_to_come_reskins_the_default(tmp_path, monkeypatch) -> None:
    session_id, _ = launch_vesper(tmp_path, monkeypatch)
    names = {str(row.get("name")) for row in Playthrough(session_id).simulation()["player_state"]["inventory_state"]["items"]}
    assert "Iron Dagger" not in names, names
