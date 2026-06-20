from __future__ import annotations

from app.rpg.session.new_game import RpgNewGameRequest, RpgPlayerOptions, _new_game_state


def _state_for_summary(summary: str) -> dict:
    return _new_game_state(
        RpgNewGameRequest(
            player=RpgPlayerOptions(name="Mira", pronouns="she/her", background="Wanderer", build="ranger"),
            seed=42,
            generated_class_summary=summary,
        ),
        "rpg_loadout_test",
        "2026-06-20T00:00:00Z",
    )


def test_new_game_applies_scout_starter_loadout_from_summary() -> None:
    state = _state_for_summary(
        "Road scout. Starter gear: Shortbow, Arrow bundle, Bedroll, Trail rations x4, 6 silver. "
        "Opening: Bandit Trail. Pace: Balanced. Relationship: Unknown outsider."
    )

    player = state["player"]
    inventory_by_id = {item["id"]: item for item in player["inventory"]}

    assert player["currency"] == {"gold": 0, "silver": 6, "copper": 0}
    assert {item["slot"]: item["name"] for item in player["equipment"]} == {"Ranged": "Shortbow"}
    assert inventory_by_id["shortbow"]["quantity"] == 1
    assert inventory_by_id["arrow"]["quantity"] == 20
    assert inventory_by_id["ration"]["quantity"] == 4
    assert inventory_by_id["waterskin"]["quantity"] == 1
    assert inventory_by_id["journal"]["quantity"] == 1
    assert state["metadata"]["starter_gear"] == ["Shortbow", "Arrow bundle", "Bedroll", "Trail rations x4", "6 silver"]
    assert state["narrative_affordances"]["starter_loadout"]["currency"] == player["currency"]


def test_new_game_applies_social_starter_loadout_currency_and_cloak() -> None:
    state = _state_for_summary(
        "Silver-tongued agent. Starter gear: Fine cloak, Ledger note, Rations x2, 15 silver. "
        "Opening: Merchant Job. Pace: Immediate action. Relationship: Known contact nearby."
    )

    player = state["player"]
    inventory_by_id = {item["id"]: item for item in player["inventory"]}

    assert player["currency"] == {"gold": 0, "silver": 15, "copper": 0}
    assert player["equipment"] == [{"slot": "Cloak", "name": "Fine cloak"}]
    assert inventory_by_id["fine_cloak"]["quantity"] == 1
    assert inventory_by_id["ledger_note"]["quantity"] == 1
    assert inventory_by_id["ration"]["quantity"] == 2


def test_new_game_uses_legacy_default_loadout_without_summary_gear() -> None:
    state = _new_game_state(RpgNewGameRequest(seed=42), "rpg_default_loadout", "2026-06-20T00:00:00Z")

    player = state["player"]

    assert player["currency"] == {"gold": 10, "silver": 25, "copper": 50}
    assert player["equipment"] == [
        {"slot": "Weapon", "name": "Iron dagger"},
        {"slot": "Ranged", "name": "Simple bow"},
        {"slot": "Cloak", "name": "Traveler's cloak"},
    ]
    assert state["metadata"]["starter_gear"] == []
