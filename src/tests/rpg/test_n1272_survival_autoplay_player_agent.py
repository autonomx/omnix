from __future__ import annotations

from app.rpg.session.survival_autoplay_player_agent import (
    choose_survival_autoplay_suggestion,
    promote_survival_suggestion_for_autoplay,
)


def _session(*, hunger=80, thirst=82, fatigue=78, items=None, runtime_state=None):
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
        "runtime_state": dict(runtime_state or {}),
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


def test_n1279_critical_thirst_outranks_higher_fatigue_when_drink_backed() -> None:
    promotion = choose_survival_autoplay_suggestion(
        _session(hunger=20, thirst=92, fatigue=100, items=[
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ])
    )

    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["action_kind"] == "drink_water"
    assert promotion["reason"] == "critical_thirst_backed_drink_priority"
    assert promotion["critical_thirst"] is True
    assert promotion["critical_thirst_source"] == "n1279_thirst_critical_relief_priority"


def test_n1279_critical_thirst_can_use_inventory_even_if_suggestion_projection_is_stale() -> None:
    promotion = choose_survival_autoplay_suggestion(
        _session(hunger=10, thirst=95, fatigue=10, items=[
            {"item_id": "canteen", "name": "Canteen", "quantity": 1, "tags": ["water"]},
        ])
    )

    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["command"] == "I drink Canteen"
    assert promotion["suggestion"]["source"] in {"n1233_survival_suggestion", "n1279_thirst_critical_relief_priority"}


def test_n1279_cadence_guard_keeps_drink_priority_after_capped_thirst() -> None:
    runtime_state = {
        "survival_autoplay_promotion_history": [
            {"action_kind": "rest", "needs": {"hunger": 20, "thirst": 100, "fatigue": 95}},
        ]
    }
    promotion = choose_survival_autoplay_suggestion(
        _session(hunger=20, thirst=84, fatigue=99, runtime_state=runtime_state, items=[
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ])
    )

    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["action_kind"] == "drink_water"
    assert promotion["reason"] == "critical_thirst_backed_drink_priority"
    assert promotion["cadence_guard_active"] is True


def test_n1279_repeated_critical_drink_is_allowed_when_thirst_remains_capped() -> None:
    runtime_state = {
        "survival_autoplay_promotion_history": [
            {"action_kind": "drink_water", "needs": {"hunger": 20, "thirst": 100, "fatigue": 70}},
        ]
    }
    promotion = choose_survival_autoplay_suggestion(
        _session(hunger=20, thirst=100, fatigue=99, runtime_state=runtime_state, items=[
            {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ])
    )

    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["reason"] == "critical_thirst_cadence_repeat_drink"
    assert promotion["previous_relief_action_kind"] == "drink_water"
