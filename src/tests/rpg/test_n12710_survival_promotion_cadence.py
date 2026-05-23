from __future__ import annotations

from app.rpg.session.survival_autoplay_cadence import apply_critical_thirst_hard_override
from app.rpg.session.survival_autoplay_relief_supplies import reset_survival_autoplay_supply_grants


def _result(*, thirst=95, hunger=20, fatigue=20, items=None):
    if items is None:
        items = [
            {"item_id": "autoplay_waterskin_1", "name": "Autoplay Waterskin", "quantity": 1, "tags": ["drink", "water"]},
        ]
    climate = {
        "format_version": "n1231_climate_survival_state_v1",
        "runtime_enforced": True,
        "source": "deterministic_authoritative_turn_tick",
        "survival": {
            "hunger": hunger,
            "thirst": thirst,
            "fatigue": fatigue,
            "action_count": 42,
            "warnings": ["thirst_high"] if thirst >= 70 else [],
        },
    }
    return {
        "turn_index": 42,
        "turn_contract": {
            "climate_survival": climate,
            "resource_changes": {
                "source": "n1231_climate_survival_tick",
                "hunger_delta": 1,
                "thirst_delta": 2,
                "fatigue_delta": 1,
            },
        },
        "session": {
            "simulation_state": {
                "climate_survival": climate,
                "needs": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
                "player_state": {
                    "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "action_count": 42},
                    "inventory_state": {"items": list(items), "currency": {}},
                },
            },
            "runtime_state": {"climate_survival": climate},
            "state": {},
            "setup_payload": {"metadata": {}},
        },
    }


def test_n12710_applies_drink_override_when_critical_thirst_missed() -> None:
    result = apply_critical_thirst_hard_override(_result(thirst=95), save=False, session_key="n12710-critical")

    override = result["survival_autoplay_critical_thirst_override"]
    action = result["turn_contract"]["survival_action"]
    cadence = result["survival_autoplay_cadence_state"]

    assert override["applied"] is True
    assert override["reason"] == "critical_thirst_hard_override"
    assert override["action_kind"] == "drink_water"
    assert override["needs_before"]["thirst"] == 95
    assert override["needs_after"]["thirst"] < 95
    assert action["applied"] is True
    assert action["resource_changes"]["thirst_delta"] < 0
    assert action["resource_changes"]["inventory_consumed"]["item_id"] == "autoplay_waterskin_1"
    assert cadence["critical_thirst_override_count"] == 1
    assert cadence["last_drink_relief_turn"] == 42


def test_n12710_skips_when_drink_already_applied() -> None:
    result = _result(thirst=95)
    result["turn_contract"]["survival_action"] = {
        "applied": True,
        "matched": True,
        "action_kind": "drink_water",
        "resource_changes": {"thirst_delta": -30},
    }

    patched = apply_critical_thirst_hard_override(result, save=False, session_key="n12710-skip")

    assert patched["survival_autoplay_critical_thirst_override"]["applied"] is False
    assert patched["survival_autoplay_critical_thirst_override"]["reason"] == "drink_already_applied"


def test_n12710_skips_when_thirst_below_threshold() -> None:
    result = apply_critical_thirst_hard_override(_result(thirst=75), save=False, session_key="n12710-low")

    assert result["survival_autoplay_critical_thirst_override"]["applied"] is False
    assert result["survival_autoplay_critical_thirst_override"]["reason"] == "thirst_below_critical_threshold"


def test_n12710_hard_override_seeds_bounded_drink_when_inventory_missing() -> None:
    key = "n12710-seed-drink"
    reset_survival_autoplay_supply_grants(key)
    result = apply_critical_thirst_hard_override(_result(thirst=100, items=[]), save=False, session_key=key)

    override = result["survival_autoplay_critical_thirst_override"]
    assert override["applied"] is True
    assert override["action_kind"] == "drink_water"
    assert override["supply_summary"]["applied"] is True
    assert override["drink_item_id"].startswith("autoplay_waterskin_")
    assert result["turn_contract"]["survival_action"]["resource_changes"]["inventory_consumed"]["consumed"] is True


def test_n12710_cadence_streak_metadata_is_persisted() -> None:
    result = _result(thirst=100, items=[])
    result["session"]["runtime_state"]["survival_autoplay_cadence_state"] = {
        "consecutive_thirst_capped_turns": 2,
        "critical_thirst_override_count": 3,
    }

    patched = apply_critical_thirst_hard_override(result, save=False, session_key="n12710-streak")
    cadence = patched["survival_autoplay_cadence_state"]
    override = patched["survival_autoplay_critical_thirst_override"]

    assert override["reason"] == "critical_thirst_capped_streak_hard_override"
    assert override["hard_due_to_streak"] is True
    assert cadence["critical_thirst_override_count"] == 4
    assert cadence["last_thirst_before"] == 100
    assert cadence["last_thirst_after"] < 100
