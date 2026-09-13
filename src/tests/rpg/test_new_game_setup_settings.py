from __future__ import annotations

from typing import Any

from app.rpg.session.new_game import RpgNewGameRequest, RpgPlayerOptions, _new_game_state

NOW = "2026-06-20T00:00:00Z"
SUMMARY = "Starter gear: Shortbow, 10 gold, 20 silver. Opening: Tavern Rumor. Pace: Balanced. Relationship: Unknown outsider."


def _state(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "player": RpgPlayerOptions(name="Mira", pronouns="she/her", background="Wanderer", build="ranger"),
        "seed": 9137,
        "generated_class_summary": SUMMARY,
    }
    payload.update(overrides)
    return _new_game_state(RpgNewGameRequest(**payload), "rpg_settings", NOW)


def test_new_game_difficulty_changes_starting_resources_and_risk() -> None:
    story = _state(difficulty="story")
    harsh = _state(difficulty="harsh")

    assert story["player"]["currency"]["gold"] > harsh["player"]["currency"]["gold"]
    assert story["mechanics"]["setup_effects"]["difficulty"]["risk_label"] == "low"
    assert harsh["mechanics"]["setup_effects"]["difficulty"]["risk_label"] == "high"
    assert harsh["mechanics"]["encounter_pressure"] == "high"


def test_new_game_economy_pressure_sets_prices_and_currency() -> None:
    relaxed = _state(economy_pressure="relaxed")
    strict = _state(economy_pressure="strict")

    assert relaxed["mechanics"]["economy"]["price_multiplier"] == 0.85
    assert strict["mechanics"]["economy"]["price_multiplier"] == 1.25
    assert relaxed["player"]["currency"]["silver"] > strict["player"]["currency"]["silver"]
    assert strict["narrative_affordances"]["setup_effects"]["economy"]["service_availability"] == "scarce"


def test_new_game_world_activity_sets_living_world_flags_and_timeline() -> None:
    quiet = _state(world_activity="quiet")
    living = _state(world_activity="living_world")

    assert quiet["world"]["activity"]["living_world"] is False
    assert quiet["world"]["activity"]["activity_density"] == "low"
    assert living["world"]["activity"]["living_world"] is True
    assert living["world"]["activity"]["activity_density"] == "high"
    assert any(entry["title"] == "Living world in motion" for entry in living["timeline"])
    assert living["journal"]["entries"] == living["timeline"]


def test_new_game_combat_lethality_and_permadeath_set_defeat_rules() -> None:
    state = _state(combat_lethality="deadly", permadeath=True)

    assert state["encounter"]["safety"] == "deadly"
    assert state["mechanics"]["setup_effects"]["combat_lethality"]["encounter_pressure"] == "high"
    assert state["mechanics"]["defeat_rules"] == {
        "permadeath": True,
        "defeat_policy": "permadeath_enabled",
        "defeat_consequence": "character_death_allowed",
    }


def test_new_game_companions_toggle_controls_affordances() -> None:
    enabled = _state(companions_enabled=True)
    disabled = _state(companions_enabled=False)

    assert enabled["mechanics"]["setup_effects"]["companions"]["enabled"] is True
    assert "Look for a companion" in enabled["quick_actions"]
    assert enabled["narrative_affordances"]["suggested_actions"] == enabled["quick_actions"]
    assert disabled["mechanics"]["setup_effects"]["companions"] == {
        "enabled": False,
        "recruitment_affordance": "disabled_by_setup",
    }
    assert "Look for a companion" not in disabled["quick_actions"]
