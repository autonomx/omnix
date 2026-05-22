from __future__ import annotations

from app.rpg.session.survival_autoplay_player_agent import (
    choose_survival_autoplay_suggestion,
    promote_survival_suggestion_for_autoplay,
)


def _session(*, hunger=80, thirst=82, fatigue=78, items=None):
    if items is None:
        items = [
            {"item_id": "trail_ration", "name": "Trail Ration", "quantity": 1, "tags": ["food"]},
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ]
    return {
        "simulation_state": {
            "climate_survival": {
                "survival": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "warnings": []},
            },
            "player_state": {
                "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
                "inventory_state": {"items": items, "currency": {"gold": 1, "silver": 10, "copper": 20}},
            },
        },
        "runtime_state": {},
    }


def test_n1272_promotes_highest_pressure_backed_survival_suggestion() -> None:
    promotion = choose_survival_autoplay_suggestion(_session(hunger=80, thirst=92, fatigue=78))

    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["action_kind"] == "drink_water"
    assert promotion["command"] == "I drink Waterskin"
    assert promotion["suggestion"]["source"] == "n1233_survival_suggestion"


def test_n1272_promotes_rest_when_fatigue_is_highest_and_no_consumable_needed() -> None:
    promotion = choose_survival_autoplay_suggestion(_session(hunger=10, thirst=20, fatigue=88, items=[]))

    assert promotion["promoted"] is True
    assert promotion["need"] == "fatigue"
    assert promotion["action_kind"] == "rest"
    assert promotion["command"] == "I rest"


def test_n1272_does_not_promote_when_no_backed_inventory_or_service_suggestions() -> None:
    promotion = choose_survival_autoplay_suggestion(_session(hunger=85, thirst=86, fatigue=10, items=[]))

    assert promotion["promoted"] is False
    assert promotion["reason"] == "no_backed_survival_suggestions"


def test_n1272_promote_survival_suggestion_returns_replacement_metadata() -> None:
    player_input, promotion = promote_survival_suggestion_for_autoplay(
        _session(hunger=80, thirst=92, fatigue=78),
        "I investigate the road.",
    )

    assert player_input == "I drink Waterskin"
    assert promotion["promoted"] is True
    assert promotion["original_player_input"] == "I investigate the road."
    assert promotion["original_was_survival_command"] is False


def test_n1272_promote_survival_suggestion_preserves_normal_input_when_pressure_low() -> None:
    player_input, promotion = promote_survival_suggestion_for_autoplay(
        _session(hunger=10, thirst=12, fatigue=14),
        "I ask Bran about the road.",
    )

    assert player_input == "I ask Bran about the road."
    assert promotion["promoted"] is False
    assert promotion["reason"] == "survival_pressure_below_threshold"
