"""The play screen's needs: hunger, thirst and fatigue as the survival rules keep them, with the levels the rules
decide, so the screen holds no thresholds and reads no simulation state of its own."""
from __future__ import annotations

from app.apps.rpg.edge.api.payloads.player_view import player_session_view
from app.apps.rpg.rules.survival import NEED_CRITICAL_AT, NEED_WARNING_AT, need_level


def _needs(simulation: dict) -> dict:
    return player_session_view({"state": {}, "simulation_state": simulation})["needs"]


def test_each_need_carries_its_level_and_the_most_pressing_one_leads() -> None:
    assert _needs({"survival": {"hunger": 72, "thirst": 41, "fatigue": 86}}) == {
        "hunger": {"value": 72, "level": "warning"},
        "thirst": {"value": 41, "level": "stable"},
        "fatigue": {"value": 86, "level": "critical"},
        "level": "critical",
    }


def test_the_levels_turn_at_the_rules_thresholds() -> None:
    assert [need_level(value) for value in (0, NEED_WARNING_AT - 1, NEED_WARNING_AT, NEED_CRITICAL_AT - 1,
                                            NEED_CRITICAL_AT, 100)] == [
        "stable", "stable", "warning", "warning", "critical", "critical"]


def test_the_stored_record_wins_over_an_older_shape_and_values_stay_in_range() -> None:
    # A campaign from before the engine can still hold a climate copy; the rules read the stored record.
    needs = _needs({"survival": {"hunger": 130, "thirst": -4, "fatigue": 10},
                    "climate_survival": {"survival": {"hunger": 5, "thirst": 90, "fatigue": 90}}})
    assert (needs["hunger"]["value"], needs["thirst"]["value"], needs["fatigue"]["value"]) == (100, 0, 10)


def test_a_campaign_without_a_record_reads_its_older_shape_or_nothing() -> None:
    assert _needs({"climate_survival": {"survival": {"hunger": 61, "thirst": 0, "fatigue": 0}}})["hunger"] == {
        "value": 61, "level": "warning"}
    assert _needs({})["level"] == "stable"
