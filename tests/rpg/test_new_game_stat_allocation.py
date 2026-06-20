from __future__ import annotations

from typing import Any

from app.rpg.session.new_game import RpgNewGameRequest, RpgPlayerOptions, STARTING_BUILDS, _new_game_state


NOW = "2026-06-20T00:00:00Z"


def _state(initial_stats: dict[str, object] | None = None, *, build: str = "ranger") -> dict[str, Any]:
    request = RpgNewGameRequest(
        player=RpgPlayerOptions(name="Mira", pronouns="she/her", background="Wanderer", build=build),
        seed=9137,
        initial_stats=initial_stats or {},
    )
    return _new_game_state(request, "rpg_test", NOW)


def test_new_game_initial_stats_drive_backend_core_stats() -> None:
    state = _state(
        {
            "strength": 15,
            "agility": 12,
            "endurance": 14,
            "intellect": 11,
            "charisma": 10,
            "perception": 13,
            "archery": 16,
            "survival": 15,
        }
    )

    assert state["player"]["stats"] == {
        "strength": 15,
        "dexterity": 12,
        "constitution": 14,
        "intelligence": 11,
        "wisdom": 13,
        "charisma": 10,
    }
    assert state["player"]["resources"] == {
        "hp": {"current": 129, "max": 129},
        "stamina": {"current": 126, "max": 126},
        "mana": {"current": 42, "max": 42},
    }
    assert state["metadata"]["stat_source"] == "new_game_point_buy"
    assert state["metadata"]["initial_stats"]["archery"] == 16
    assert state["skill_progression"]["starting_stats"]["survival"] == {
        "value": 15,
        "source": "new_game_point_buy",
    }
    assert state["narrative_affordances"]["stat_profile"]["rpg_only_stats"] == {"archery": 16, "survival": 15}


def test_new_game_missing_stats_fall_back_to_build_defaults() -> None:
    state = _state(build="silver_tongue")
    build = STARTING_BUILDS["silver_tongue"]

    assert state["metadata"]["stat_source"] == "build_default"
    assert state["metadata"]["initial_stats"] == {}
    assert state["player"]["stats"] == build["stats"]
    assert state["player"]["resources"] == {"hp": build["hp"], "stamina": build["stamina"], "mana": build["mana"]}


def test_new_game_invalid_stats_fall_back_per_key_and_clamp_ranges() -> None:
    state = _state(
        {
            "strength": "not-a-number",
            "agility": 99,
            "endurance": 4,
            "intellect": 12.5,
            "charisma": True,
            "perception": "15",
            "archery": None,
            "survival": "16",
        },
        build="warrior",
    )

    assert state["player"]["stats"] == {
        "strength": 14,
        "dexterity": 16,
        "constitution": 8,
        "intelligence": 8,
        "wisdom": 15,
        "charisma": 9,
    }
    assert state["metadata"]["initial_stats"] == {"agility": 16, "endurance": 8, "perception": 15, "survival": 16}
    assert state["narrative_affordances"]["stat_profile"]["rpg_only_stats"] == {"survival": 16}


def test_new_game_derived_resources_are_deterministic() -> None:
    stats = {
        "strength": 11,
        "agility": 13,
        "endurance": 16,
        "intellect": 14,
        "charisma": 12,
        "perception": 15,
        "archery": 10,
        "survival": 14,
    }
    first = _state(stats, build="balanced_adventurer")
    second = _state(stats, build="balanced_adventurer")

    assert first["player"]["resources"] == second["player"]["resources"]
    assert first["player"]["stats"] == second["player"]["stats"]
    assert first["metadata"]["initial_stats"] == second["metadata"]["initial_stats"]
