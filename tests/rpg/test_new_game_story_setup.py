from __future__ import annotations

from app.rpg.session.new_game import RpgNewGameRequest, RpgPlayerOptions, _new_game_state
from app.rpg.session.starter_kit import build_starter_kit


def test_new_game_story_setup_seeds_objective_relationship_and_actions() -> None:
    request = RpgNewGameRequest(
        player=RpgPlayerOptions(name="Mira", pronouns="she/her", background="Wanderer", build="ranger"),
        seed=9137,
        generated_class_summary="Road scout. Opening: Merchant Job. Pace: Immediate action. Relationship: Known contact nearby.",
    )

    state = _new_game_state(request, "rpg_test", "2026-06-20T00:00:00Z")

    assert state["metadata"]["opening_hook"] == "merchant_job"
    assert state["metadata"]["opening_pace"] == "immediate_action"
    assert state["metadata"]["relationship_preset"] == "known_contact_nearby"
    assert state["quests"] == [
        {
            "id": "merchant_job",
            "title": "Merchant's Ledger",
            "status": "active",
            "objective": "Speak with Elara about a paid delivery job before leaving the tavern.",
        }
    ]
    assert state["relationships"] == [{"name": "Elara", "stance": "Contact", "score": 24, "role": "Merchant"}]
    assert state["quick_actions"][0] == "Speak with Elara"
    assert state["narrative_affordances"]["opening_story"]["opening_hook_label"] == "Merchant Job"
    assert state["narrative_affordances"]["suggested_actions"] == state["quick_actions"]
    assert any(entry["title"] == "Merchant job offered" for entry in state["timeline"])
    assert any(entry["title"] == "Known contact nearby" for entry in state["journal"]["entries"])


def test_new_game_random_story_hook_is_seed_deterministic() -> None:
    request = RpgNewGameRequest(
        seed=7,
        generated_class_summary="Opening: Random from Seed. Pace: Slow roleplay. Relationship: Guard suspicion.",
    )

    first = _new_game_state(request, "rpg_a", "2026-06-20T00:00:00Z")
    second = _new_game_state(request, "rpg_b", "2026-06-20T00:00:00Z")

    assert first["metadata"]["opening_hook"] == second["metadata"]["opening_hook"]
    assert first["metadata"]["opening_hook"] == "missing_person"
    assert first["metadata"]["opening_pace"] == "slow_roleplay"
    assert first["metadata"]["relationship_preset"] == "guard_suspicion"
    assert first["relationships"] == [{"name": "Captain Aldric", "stance": "Suspicious", "score": -12, "role": "Guard"}]
    assert first["quick_actions"][0] == "Take in the scene"


def test_new_game_story_setup_uses_safe_defaults() -> None:
    state = _new_game_state(
        RpgNewGameRequest(generated_class_summary="Opening: unknown. Pace: unknown. Relationship: unknown."),
        "rpg_default",
        "2026-06-20T00:00:00Z",
    )

    assert state["metadata"]["opening_hook"] == "tavern_rumor"
    assert state["metadata"]["opening_pace"] == "balanced"
    assert state["metadata"]["relationship_preset"] == "unknown_outsider"
    assert state["quests"][0]["id"] == "tavern_rumor"
    assert state["relationships"] == []


def test_starter_kit_parser_applies_generated_gear_currency_and_equipment() -> None:
    starter = build_starter_kit("Road scout. Starter gear: Shortbow, Arrow bundle, Bedroll, Trail rations x4, 6 silver. Opening: Bandit Trail.")

    inventory = {item["id"]: item for item in starter["inventory"]}
    assert starter["source"] == "generated_class_summary"
    assert starter["currency"] == {"gold": 0, "silver": 6, "copper": 0}
    assert inventory["shortbow"]["quantity"] == 1
    assert inventory["arrow"]["quantity"] == 20
    assert inventory["ration"]["quantity"] == 4
    assert inventory["bedroll"]["quantity"] == 1
    assert inventory["journal"]["quantity"] == 1
    assert starter["equipment"] == [{"slot": "Ranged", "name": "Shortbow"}]


def test_new_game_applies_starter_kit_to_player_state() -> None:
    state = _new_game_state(
        RpgNewGameRequest(
            seed=123,
            generated_class_summary="Road scout. Starter gear: Shortbow, Arrow bundle, Bedroll, Trail rations x4, 6 silver. Opening: Bandit Trail.",
        ),
        "rpg_starter",
        "2026-06-20T00:00:00Z",
    )

    inventory = {item["id"]: item for item in state["player"]["inventory"]}
    assert state["metadata"]["starter_kit_source"] == "generated_class_summary"
    assert state["player"]["currency"] == {"gold": 0, "silver": 6, "copper": 0}
    assert inventory["shortbow"]["name"] == "Shortbow"
    assert inventory["ration"]["quantity"] == 4
    assert state["player"]["equipment"] == [{"slot": "Ranged", "name": "Shortbow"}]
    assert state["narrative_affordances"]["starter_kit"]["source"] == "generated_class_summary"


def test_starter_kit_falls_back_to_default_inventory_and_currency() -> None:
    state = _new_game_state(RpgNewGameRequest(), "rpg_default_kit", "2026-06-20T00:00:00Z")

    inventory = {item["id"]: item for item in state["player"]["inventory"]}
    assert state["metadata"]["starter_kit_source"] == "default"
    assert state["player"]["currency"] == {"gold": 10, "silver": 25, "copper": 50}
    assert inventory["iron_dagger"]["quantity"] == 1
    assert inventory["ration"]["quantity"] == 3
    assert state["player"]["equipment"] == [
        {"slot": "Weapon", "name": "Iron dagger"},
        {"slot": "Ranged", "name": "Simple bow"},
        {"slot": "Cloak", "name": "Traveler's cloak"},
    ]
