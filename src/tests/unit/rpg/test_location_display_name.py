"""A scene never names a location by its id ("loc_tavern" became "Loc Tavern" in narration)."""
from __future__ import annotations

from app.apps.rpg.session.combat_intent import _apply_grounded_scene_overlay, _resolve_location_name


def test_the_registry_names_a_location_whose_state_entry_has_no_name() -> None:
    simulation = {"locations": {"loc_tavern": {"heat": 3, "status": "active"}}}
    assert _resolve_location_name(simulation, "loc_tavern", "loc_tavern") == "The Rusty Flagon Tavern"


def test_an_unknown_location_reads_as_words_not_as_its_id() -> None:
    assert _resolve_location_name({}, "loc_sunken_chapel", "loc_sunken_chapel") == "Sunken Chapel"
    assert _resolve_location_name({}, "loc_sunken_chapel", "The Sunken Chapel") == "The Sunken Chapel"


def test_a_stored_id_valued_name_is_replaced_by_the_grounded_name() -> None:
    scene = _apply_grounded_scene_overlay(
        {"location_id": "loc_tavern", "location_name": "loc_tavern"},
        {"location_name": "The Rusty Flagon Tavern"},
    )
    assert scene["location_name"] == "The Rusty Flagon Tavern"
