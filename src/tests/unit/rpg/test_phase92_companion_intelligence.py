"""Unit tests for Phase 9.2 — Companion Intelligence Layer."""
import pytest

from app.rpg.party.party_state import (
    ensure_party_state,
    add_companion,
    update_companion_hp,
    update_companion_loyalty,
    update_companion_morale,
    set_companion_status,
    set_companion_equipment,
    clear_companion_equipment,
    build_party_summary,
    remove_companion,
    get_active_companions,
)
from app.rpg.party.companion_ai import choose_companion_action, run_companion_turns


def _base_companion_state():
    return {
        "party_state": {
            "companions": [
                {
                    "npc_id": "npc_1",
                    "name": "A",
                    "role": "guard",
                    "hp": 100,
                    "max_hp": 100,
                    "loyalty": 0.5,
                    "morale": 0.5,
                    "status": "active",
                    "equipment": {},
                }
            ],
            "max_size": 3,
        }
    }


def test_update_companion_hp_damage_does_not_go_below_zero():
    player_state = _base_companion_state()
    out = update_companion_hp(player_state, "npc_1", -150)
    comp = out["party_state"]["companions"][0]
    assert comp["hp"] == 0
    assert comp["status"] == "downed"


def test_update_companion_hp_heal_does_not_exceed_max():
    player_state = _base_companion_state()
    player_state["party_state"]["companions"][0]["hp"] = 50
    out = update_companion_hp(player_state, "npc_1", 100)
    comp = out["party_state"]["companions"][0]
    assert comp["hp"] == 100
    assert comp["status"] == "active"


def test_update_companion_hp_sets_downed_when_zero():
    player_state = _base_companion_state()
    player_state["party_state"]["companions"][0]["hp"] = 10
    out = update_companion_hp(player_state, "npc_1", -10)
    assert out["party_state"]["companions"][0]["status"] == "downed"
    assert out["party_state"]["companions"][0]["hp"] == 0


def test_update_companion_loyalty_clamps_upper():
    player_state = _base_companion_state()
    out = update_companion_loyalty(player_state, "npc_1", 1.0)
    assert out["party_state"]["companions"][0]["loyalty"] == 1.0


def test_update_companion_loyalty_clamps_lower():
    player_state = _base_companion_state()
    out = update_companion_loyalty(player_state, "npc_1", -2.0)
    assert out["party_state"]["companions"][0]["loyalty"] == -1.0


def test_update_companion_morale_clamps():
    player_state = _base_companion_state()
    out = update_companion_morale(player_state, "npc_1", 1.0)
    assert out["party_state"]["companions"][0]["morale"] == 1.0

    out = update_companion_morale(player_state, "npc_1", -2.0)
    assert out["party_state"]["companions"][0]["morale"] == 0.0


def test_set_companion_status():
    player_state = _base_companion_state()
    out = set_companion_status(player_state, "npc_1", "absent")
    assert out["party_state"]["companions"][0]["status"] == "absent"


def test_set_and_clear_companion_equipment():
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_1", "A")
    player_state = set_companion_equipment(player_state, "npc_1", "weapon", "fire_sword")
    comp = player_state["party_state"]["companions"][0]
    # Equipment now stores item_id as string directly (pointer model)
    assert comp["equipment"]["weapon"] == "fire_sword"

    player_state = clear_companion_equipment(player_state, "npc_1", "weapon")
    comp = player_state["party_state"]["companions"][0]
    assert "weapon" not in comp["equipment"]


def test_choose_companion_action_hesitate_on_low_loyalty():
    companion = {
        "npc_id": "npc_1",
        "name": "A",
        "role": "guard",
        "hp": 100,
        "max_hp": 100,
        "loyalty": -0.8,
        "morale": 0.5,
        "status": "active",
        "equipment": {},
    }
    encounter_state = {"status": "active", "participants": []}
    action = choose_companion_action(companion, encounter_state)
    assert action["action_type"] == "hesitate"


def test_choose_companion_action_defend_on_low_hp():
    companion = {
        "npc_id": "npc_1",
        "name": "A",
        "role": "guard",
        "hp": 10,
        "max_hp": 100,
        "loyalty": 0.5,
        "morale": 0.5,
        "status": "active",
        "equipment": {},
    }
    encounter_state = {
        "status": "active",
        "participants": [{"id": "enemy_1", "role": "enemy", "disposition": "hostile"}],
    }
    action = choose_companion_action(companion, encounter_state)
    assert action["action_type"] == "defend"


def test_choose_companion_action_attack_when_hostile():
    companion = {
        "npc_id": "npc_1",
        "name": "A",
        "role": "guard",
        "hp": 100,
        "max_hp": 100,
        "loyalty": 0.5,
        "morale": 0.5,
        "status": "active",
        "equipment": {},
    }
    encounter_state = {
        "status": "active",
        "participants": [{"id": "enemy_1", "role": "enemy", "disposition": "hostile"}],
    }
    action = choose_companion_action(companion, encounter_state)
    assert action["action_type"] == "attack"
    assert action["target_id"] == "enemy_1"


def test_choose_companion_action_heal_self_when_support_low_hp():
    companion = {
        "npc_id": "npc_1",
        "name": "A",
        "role": "support",
        "hp": 40,
        "max_hp": 100,
        "loyalty": 0.8,
        "morale": 0.8,
        "status": "active",
        # Equipment now stores item_id as string directly (pointer model)
        "equipment": {"consumable": "healing_potion"},
    }
    encounter_state = {
        "status": "active",
        "participants": [{"id": "enemy_1", "role": "enemy", "disposition": "hostile"}],
    }
    action = choose_companion_action(companion, encounter_state)
    assert action["action_type"] == "heal_self"


def test_run_companion_turns_does_not_run_on_resolved():
    sim_state = {
        "player_state": ensure_party_state({
            "party_state": {
                "companions": [{"npc_id": "npc_1", "name": "A", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "active", "role": "guard", "equipment": {}}],
                "max_size": 3,
            }
        })
    }
    encounter_state = {"status": "resolved", "log": []}
    result = run_companion_turns(sim_state, encounter_state)
    assert result.get("log") == []


def test_build_party_summary_empty_party():
    player_state = ensure_party_state({})
    summary = build_party_summary(player_state)
    assert summary["size"] == 0


def test_build_party_summary_with_companions():
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_1", "A")
    player_state = add_companion(player_state, "npc_2", "B")
    summary = build_party_summary(player_state)
    assert summary["size"] == 2
    assert summary["active_count"] == 2
    assert summary["downed_count"] == 0


def test_companions_deduplicated_on_ensure():
    player_state = {
        "party_state": {
            "companions": [
                {"npc_id": "npc_1", "name": "A", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "guard", "status": "active", "equipment": {}},
                {"npc_id": "npc_1", "name": "A_dup", "hp": 50, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "guard", "status": "active", "equipment": {}},
            ],
            "max_size": 3,
        }
    }
    out = ensure_party_state(player_state)
    companion_ids = [c["npc_id"] for c in out["party_state"]["companions"]]
    assert companion_ids.count("npc_1") == 1


def test_add_companion_respects_max_size():
    player_state = {
        "party_state": {
            "companions": [
                {"npc_id": "c1", "name": "C1", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "ally", "status": "active", "equipment": {}},
                {"npc_id": "c2", "name": "C2", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "ally", "status": "active", "equipment": {}},
                {"npc_id": "c3", "name": "C3", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "ally", "status": "active", "equipment": {}},
            ],
            "max_size": 3,
        }
    }
    out = add_companion(player_state, "c4", "C4")
    assert len(out["party_state"]["companions"]) == 3


def test_get_active_companions_filters_downed():
    player_state = {
        "party_state": {
            "companions": [
                {"npc_id": "c1", "name": "C1", "hp": 0, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "ally", "status": "downed", "equipment": {}},
                {"npc_id": "c2", "name": "C2", "hp": 50, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "role": "ally", "status": "active", "equipment": {}},
            ],
            "max_size": 3,
        }
    }
    active = get_active_companions(player_state)
    assert len(active) == 1
    assert active[0]["npc_id"] == "c2"