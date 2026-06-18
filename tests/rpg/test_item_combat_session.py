from __future__ import annotations

from app.rpg.session.item_combat_session import apply_session_item_combat, find_session_combat_actor


def _state() -> dict[str, object]:
    return {
        "turn": 7,
        "player": {
            "id": "player",
            "name": "Hero",
            "equipment": [
                {
                    "item_id": "training_blade",
                    "name": "Training Blade",
                    "slot": "Weapon",
                    "damage": {"slashing": 6},
                }
            ],
        },
        "npcs": [
            {
                "id": "sparring_partner",
                "name": "Sparring Partner",
                "resources": {"health": {"current": 9, "max": 9}},
                "equipment": [
                    {
                        "item_id": "padded_guard",
                        "name": "Padded Guard",
                        "slot": "Body",
                        "defense": {"slashing": 2},
                    }
                ],
            }
        ],
        "mechanics": {},
    }


def test_find_session_combat_actor_defaults_to_player_and_matches_npc() -> None:
    state = _state()

    assert find_session_combat_actor(state, None, default_player=True)["id"] == "player"
    assert find_session_combat_actor(state, "sparring_partner")["name"] == "Sparring Partner"


def test_apply_session_item_combat_mutates_defender_resource_and_writes_traces() -> None:
    state = _state()

    result = apply_session_item_combat(state, defender_id="sparring_partner")

    assert result["ok"] is True
    assert result["effects"] == [{"resource": "health", "before": 9, "after": 5, "delta": -4}]
    defender = state["npcs"][0]
    assert defender["resources"]["health"]["current"] == 5
    assert state["mechanics"]["item_combat_traces"][0]["event"] == "session_item_combat_applied"
    assert state["mechanics"]["item_combat_traces"][0]["total_resolved"] == 4
    assert state["mechanics"]["item_traces"][0]["mechanics_source"] == "engine_session_item_combat_v1"


def test_apply_session_item_combat_reports_missing_actor_without_trace_noise() -> None:
    state = _state()

    result = apply_session_item_combat(state, defender_id="missing")

    assert result == {
        "ok": False,
        "error": "defender_not_found",
        "detail": "No defender was found for the item combat action.",
    }
    assert state["mechanics"] == {}


def test_apply_session_item_combat_supports_actor_map_and_unarmed_fallback() -> None:
    state = {
        "actors": {
            "scout": {"id": "scout", "name": "Scout"},
            "dummy": {"id": "dummy", "name": "Dummy", "health": 3},
        },
        "mechanics": {},
    }

    result = apply_session_item_combat(state, attacker_id="scout", defender_id="dummy")

    assert result["ok"] is True
    assert result["source_item"]["item_id"] == "unarmed"
    assert state["actors"]["dummy"]["health"] == 2
    assert result["effects"][0]["after"] == 2
}
