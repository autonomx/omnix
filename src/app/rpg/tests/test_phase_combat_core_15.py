from app.rpg.combat.initiative import advance_turn, begin_combat
from app.rpg.combat.lifecycle import evaluate_combat_exit
from app.rpg.combat.npc_turns import run_npc_turn
from app.rpg.combat.state import build_empty_combat_state, get_current_actor_id


def _sim():
    return {
        "actor_states": [
            {
                "id": "player",
                "type": "player",
                "is_player": True,
                "combat_team": "player",
                "stats": {"strength": 3, "agility": 3},
                "skills": {"brawling": 2, "awareness": 2},
                "resources": {"hp": 10},
                "status_effects": [],
                "name": "Player",
            }
        ],
        "npc_states": [
            {
                "id": "bran",
                "combat_team": "hostile",
                "stats": {"strength": 2, "agility": 1, "endurance": 1},
                "skills": {"evasion": 1, "awareness": 1},
                "resources": {"hp": 8},
                "status_effects": [],
                "name": "Bran the Innkeeper",
            }
        ],
    }


def test_begin_combat_builds_deterministic_turn_order():
    sim = _sim()
    state = begin_combat(
        sim,
        build_empty_combat_state(),
        ["player", "bran"],
        combat_id="combat:test",
        tick=5,
        initial_target_id="bran",
    )
    assert state["active"] is True
    assert state["round"] == 1
    assert state["turn_order"] == begin_combat(
        sim,
        build_empty_combat_state(),
        ["player", "bran"],
        combat_id="combat:test",
        tick=5,
        initial_target_id="bran",
    )["turn_order"]


def test_advance_turn_cycles_round():
    state = build_empty_combat_state()
    state.update({
        "active": True,
        "phase": "active",
        "turn_order": ["a", "b"],
        "turn_index": 1,
        "round": 1,
        "current_actor_id": "b",
    })
    state = advance_turn(state)
    assert state["turn_index"] == 0
    assert state["round"] == 2
    assert get_current_actor_id(state) == "a"


def test_npc_turn_executes_and_advances():
    sim = _sim()
    state = begin_combat(
        sim,
        build_empty_combat_state(),
        ["player", "bran"],
        combat_id="combat:test",
        tick=5,
        initial_target_id="player",
    )
    if get_current_actor_id(state) == "player":
        state = advance_turn(state)

    sim2, state2, npc_resolution = run_npc_turn(sim, state, tick=5)
    assert isinstance(npc_resolution, dict)
    assert state2["round"] >= 1


def test_evaluate_combat_exit_resolves_last_team_standing():
    sim = _sim()
    sim["npc_states"][0]["resources"]["hp"] = 0
    sim["npc_states"][0]["status_effects"] = ["downed"]

    state = begin_combat(
        sim,
        build_empty_combat_state(),
        ["player", "bran"],
        combat_id="combat:test",
        tick=5,
        initial_target_id="bran",
    )
    state = evaluate_combat_exit(sim, state)
    assert state["active"] is False
    assert state["phase"] == "resolved"
    assert state["exit_reason"] in {"last_team_standing", "all_downed"}
