from app.rpg.combat.models import AttackIntent
from app.rpg.combat.resolver import resolve_attack
from app.rpg.combat.apply import apply_attack_resolution
from app.rpg.combat.state import build_empty_combat_state


def _sim():
    return {
        "actor_states": [
            {
                "id": "player",
                "stats": {"strength": 3, "agility": 2},
                "skills": {"brawling": 2},
                "resources": {"hp": 10},
                "status_effects": [],
            }
        ],
        "npc_states": [
            {
                "id": "bran",
                "stats": {"strength": 2, "agility": 1, "endurance": 1},
                "skills": {"evasion": 1},
                "resources": {"hp": 8},
                "status_effects": [],
            }
        ],
    }


def test_resolve_attack_is_deterministic():
    sim = _sim()
    state = build_empty_combat_state()
    state["active"] = True
    state["combat_id"] = "combat:test"

    intent = AttackIntent(actor_id="player", target_id="bran", action_type="unarmed_attack")
    a = resolve_attack(sim, state, intent, turn_id="turn:5", tick=5).to_dict()
    b = resolve_attack(sim, state, intent, turn_id="turn:5", tick=5).to_dict()

    assert a == b


def test_apply_attack_resolution_updates_hp():
    sim = _sim()
    state = build_empty_combat_state()
    state["active"] = True
    state["combat_id"] = "combat:test"

    intent = AttackIntent(actor_id="player", target_id="bran", action_type="unarmed_attack")
    resolution = resolve_attack(sim, state, intent, turn_id="turn:5", tick=5).to_dict()

    sim2, state2 = apply_attack_resolution(sim, state, resolution)

    bran = next(x for x in sim2["npc_states"] if x["id"] == "bran")
    assert bran["resources"]["hp"] == resolution["target_hp_after"]
    assert state2["last_resolution"]["target_id"] == "bran"
