from __future__ import annotations

from app.rpg.session.survival_autoplay_player_agent import choose_survival_autoplay_suggestion
from app.rpg.session.survival_autoplay_relief_supplies import (
    ensure_survival_autoplay_relief_supplies,
    reset_survival_autoplay_supply_grants,
)
from app.rpg.session.survival_actions import resolve_survival_action


def _session(*, hunger=70, thirst=80, fatigue=10):
    climate = {
        "format_version": "n1231_climate_survival_state_v1",
        "runtime_enforced": True,
        "source": "deterministic_authoritative_turn_tick",
        "survival": {
            "hunger": hunger,
            "thirst": thirst,
            "fatigue": fatigue,
            "action_count": 50,
            "warnings": ["hunger_high", "thirst_high"],
        },
    }
    return {
        "simulation_state": {
            "climate_survival": climate,
            "needs": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
            "player_state": {
                "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "action_count": 50},
                "inventory_state": {"items": [], "currency": {}},
            },
        },
        "runtime_state": {"climate_survival": climate},
        "state": {},
        "setup_payload": {"metadata": {}},
    }


def test_n1276_seeds_bounded_food_and_drink_when_pressure_has_no_relief() -> None:
    key = "n1276-seed"
    reset_survival_autoplay_supply_grants(key)

    session, summary = ensure_survival_autoplay_relief_supplies(_session(), session_key=key)

    assert summary["applied"] is True
    assert summary["grant_count"] == 2
    assert {grant["kind"] for grant in summary["grants"]} == {"food", "drink"}
    items = session["simulation_state"]["player_state"]["inventory_state"]["items"]
    item_ids = {item["item_id"] for item in items}
    assert "autoplay_field_ration_1" in item_ids
    assert "autoplay_waterskin_1" in item_ids
    assert session["runtime_state"]["survival_autoplay_relief_supply_grants"] == {"food": 1, "drink": 1}


def test_n1276_seeded_supplies_create_hunger_thirst_suggestions() -> None:
    key = "n1276-selector"
    reset_survival_autoplay_supply_grants(key)
    session, summary = ensure_survival_autoplay_relief_supplies(_session(hunger=65, thirst=90, fatigue=10), session_key=key)

    promotion = choose_survival_autoplay_suggestion(session)

    assert summary["applied"] is True
    assert promotion["promoted"] is True
    assert promotion["need"] == "thirst"
    assert promotion["action_kind"] == "drink_water"
    assert "drink" in promotion["command"].lower()


def test_n1276_seeded_drink_is_consumed_by_existing_resolver() -> None:
    key = "n1276-consume"
    reset_survival_autoplay_supply_grants(key)
    session, _summary = ensure_survival_autoplay_relief_supplies(_session(hunger=65, thirst=90, fatigue=10), session_key=key)
    simulation_state = session["simulation_state"]

    result = resolve_survival_action(player_input="I drink Autoplay Waterskin", simulation_state=simulation_state)

    assert result["applied"] is True
    assert result["action_kind"] == "drink_water"
    assert result["resource_changes"]["thirst_delta"] < 0
    assert result["resource_changes"]["inventory_consumed"]["item_id"] == "autoplay_waterskin_1"
    remaining_ids = {item["item_id"] for item in simulation_state["player_state"]["inventory_state"]["items"]}
    assert "autoplay_waterskin_1" not in remaining_ids


def test_n1276_supply_grants_are_bounded_per_session() -> None:
    key = "n1276-bounded"
    reset_survival_autoplay_supply_grants(key)
    session = _session()
    summaries = []

    for _ in range(4):
        session, summary = ensure_survival_autoplay_relief_supplies(session, session_key=key)
        summaries.append(summary)
        # Simulate consumption between turns so the helper may try to refill.
        session["simulation_state"]["player_state"]["inventory_state"]["items"] = []

    assert summaries[0]["grant_count"] == 2
    assert summaries[1]["grant_count"] == 2
    assert summaries[2]["grant_count"] == 0
    assert summaries[3]["grant_count"] == 0
    assert session["runtime_state"]["survival_autoplay_relief_supply_grants"] == {"food": 2, "drink": 2}


def test_n1276_does_not_seed_when_pressure_is_low() -> None:
    key = "n1276-low"
    reset_survival_autoplay_supply_grants(key)

    session, summary = ensure_survival_autoplay_relief_supplies(_session(hunger=10, thirst=20, fatigue=10), session_key=key)

    assert summary["applied"] is False
    assert summary["grant_count"] == 0
    assert session["simulation_state"]["player_state"]["inventory_state"]["items"] == []
