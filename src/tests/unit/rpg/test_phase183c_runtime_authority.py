from __future__ import annotations

from typing import Any, Dict

import pytest


def _base_session():
    return {
        "manifest": {
            "id": "sess_test_authority",
            "title": "Authority Test",
            "status": "active",
            "created_at": "2026-04-07T00:00:00Z",
            "updated_at": "2026-04-07T00:00:00Z",
            "schema_version": 3,
            "archived": False,
        },
        "setup_payload": {
            "metadata": {
                "simulation_state": {},
            },
        },
        "simulation_state": {
            "tick": 0,
            "player_state": {
                "name": "Hero",
                "location_id": "loc:test",
                "stats": {
                    "strength": 14,
                    "dexterity": 12,
                    "constitution": 10,
                    "intelligence": 10,
                    "wisdom": 10,
                    "charisma": 10,
                },
                "skills": {
                    "swordsmanship": {"level": 1, "xp": 0, "xp_to_next": 25},
                    "archery": {"level": 0, "xp": 0, "xp_to_next": 25},
                },
                "level": 1,
                "xp": 0,
                "xp_to_next": 100,
                "inventory_state": {
                    "items": [
                        {
                            "item_id": "iron_sword",
                            "name": "Iron Sword",
                            "qty": 1,
                            "equipment": {"slot": "main_hand"},
                            "combat_stats": {"damage": 28, "weapon_type": "sword"},
                        }
                    ],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {},
                    "last_loot": [],
                },
                "nearby_npc_ids": [],
                "available_checks": [],
            },
            "world_items": {
                "by_location": {
                    "loc:test": [
                        {
                            "instance_id": "wi:test:shield:0",
                            "item_id": "wooden_shield",
                            "name": "Wooden Shield",
                            "qty": 1,
                            "equipment": {"slot": "off_hand"},
                            "combat_stats": {"defense_bonus": 3},
                        }
                    ]
                }
            },
            "npcs": {
                "npc_bandit": {
                    "name": "Bandit",
                    "hp": 20,
                    "stats": {"dexterity": 10, "constitution": 10},
                }
            },
        },
        "runtime_state": {
            "tick": 0,
            "opening": "You arrive.",
            "world": {"genre": "fantasy"},
            "npcs": [{"id": "npc_bandit", "name": "Bandit"}],
            "current_scene": {
                "scene_id": "scene:test",
                "location_id": "loc:test",
                "present_npc_ids": ["npc_bandit"],
                "items": [],
                "available_checks": [],
            },
            "last_turn_result": {},
            "turn_history": [],
            "voice_assignments": {},
        },
    }


@pytest.fixture
def runtime_module():
    from app.rpg.session import runtime
    return runtime


def test_pickup_item_mutates_state_before_payload(runtime_module, monkeypatch):
    session = _base_session()

    monkeypatch.setattr(runtime_module, "load_runtime_session", lambda session_id: session)
    monkeypatch.setattr(runtime_module, "save_runtime_session", lambda s: s)
    monkeypatch.setattr(runtime_module, "step_simulation_state", lambda setup: {"next_setup": setup, "after_state": setup.get("metadata", {}).get("simulation_state", {})})
    monkeypatch.setattr(runtime_module, "generate_scenes_from_simulation", lambda state: [runtime_module._safe_dict(session["runtime_state"]["current_scene"])])
    monkeypatch.setattr(runtime_module, "summarize_simulation_step", lambda step: ["picked up item"])
    monkeypatch.setattr(runtime_module, "narrate_scene", lambda scene, ctx, tone="dramatic": {"narrative": "You pick up the **Wooden Shield**."})

    result = runtime_module.apply_turn(
        "sess_test_authority",
        "pick up the shield",
        action={"action_type": "pickup_item", "instance_id": "wi:test:shield:0"},
    )

    assert result["ok"] is True
    saved = result["session"]
    sim = saved["simulation_state"]
    inv_items = sim["player_state"]["inventory_state"]["items"]
    assert any(item.get("item_id") == "wooden_shield" for item in inv_items)
    scene_items = sim["world_items"]["by_location"]["loc:test"]
    assert not any(item.get("instance_id") == "wi:test:shield:0" for item in scene_items)
    assert "Wooden Shield" in result["payload"]["narration"]


def test_equip_item_updates_equipment(runtime_module, monkeypatch):
    session = _base_session()

    monkeypatch.setattr(runtime_module, "load_runtime_session", lambda session_id: session)
    monkeypatch.setattr(runtime_module, "save_runtime_session", lambda s: s)
    monkeypatch.setattr(runtime_module, "step_simulation_state", lambda setup: {"next_setup": setup, "after_state": setup.get("metadata", {}).get("simulation_state", {})})
    monkeypatch.setattr(runtime_module, "generate_scenes_from_simulation", lambda state: [runtime_module._safe_dict(session["runtime_state"]["current_scene"])])
    monkeypatch.setattr(runtime_module, "summarize_simulation_step", lambda step: ["equipped item"])
    monkeypatch.setattr(runtime_module, "narrate_scene", lambda scene, ctx, tone="dramatic": {"narrative": "You equip the **Iron Sword**."})

    result = runtime_module.apply_turn(
        "sess_test_authority",
        "equip the sword",
        action={"action_type": "equip_item", "item_id": "iron_sword", "slot": "main_hand"},
    )

    assert result["ok"] is True
    equipment = result["session"]["simulation_state"]["player_state"]["inventory_state"]["equipment"]
    assert equipment.get("main_hand", {}).get("item_id") == "iron_sword"


def test_attack_turn_surfaces_combat_result(runtime_module, monkeypatch):
    session = _base_session()

    monkeypatch.setattr(runtime_module, "load_runtime_session", lambda session_id: session)
    monkeypatch.setattr(runtime_module, "save_runtime_session", lambda s: s)
    monkeypatch.setattr(runtime_module, "step_simulation_state", lambda setup: {"next_setup": setup, "after_state": setup.get("metadata", {}).get("simulation_state", {})})
    monkeypatch.setattr(runtime_module, "generate_scenes_from_simulation", lambda state: [runtime_module._safe_dict(session["runtime_state"]["current_scene"])])
    monkeypatch.setattr(runtime_module, "summarize_simulation_step", lambda step: ["combat resolved"])
    monkeypatch.setattr(
        runtime_module,
        "resolve_player_action",
        lambda sim, action: {
            "simulation_state": sim,
            "result": {
                "ok": True,
                "action_type": "attack_melee",
                "combat_result": {"outcome": "hit", "damage": 9, "target_id": "npc_bandit"},
                "xp_result": {"player_xp": 10},
                "skill_xp_result": {"awards": {"swordsmanship": 3}},
            },
        },
    )
    monkeypatch.setattr(runtime_module, "narrate_scene", lambda scene, ctx, tone="dramatic": {"narrative": "You strike the bandit for **9 damage**."})

    result = runtime_module.apply_turn(
        "sess_test_authority",
        "attack the bandit",
        action={"action_type": "attack_melee", "target_id": "npc_bandit"},
    )

    assert result["ok"] is True
    payload = result["payload"]
    assert payload["combat_result"]["outcome"] == "hit"
    assert payload["combat_result"]["damage"] == 9
    assert payload["xp_result"]["player_xp"] == 10
    assert payload["skill_xp_result"]["awards"]["swordsmanship"] == 3


def test_attack_turn_uses_real_resolver(runtime_module, monkeypatch):
    session = _base_session()

    monkeypatch.setattr(runtime_module, "load_runtime_session", lambda session_id: session)
    monkeypatch.setattr(runtime_module, "save_runtime_session", lambda s: s)
    monkeypatch.setattr(
        runtime_module,
        "step_simulation_state",
        lambda setup: {"next_setup": setup, "after_state": setup.get("metadata", {}).get("simulation_state", {})},
    )
    monkeypatch.setattr(
        runtime_module,
        "generate_scenes_from_simulation",
        lambda state: [runtime_module._safe_dict(session["runtime_state"]["current_scene"])],
    )
    monkeypatch.setattr(runtime_module, "summarize_simulation_step", lambda step: ["combat resolved"])
    monkeypatch.setattr(
        runtime_module,
        "narrate_scene",
        lambda scene, ctx, tone="dramatic": {"narrative": "Combat resolves."},
    )

    # Equip the sword first
    session["simulation_state"]["player_state"]["inventory_state"]["equipment"] = {
        "main_hand": session["simulation_state"]["player_state"]["inventory_state"]["items"][0]
    }

    result = runtime_module.apply_turn(
        "sess_test_authority",
        "attack the bandit",
        action={"action_type": "attack_melee", "target": session["simulation_state"]["npcs"]["npc_bandit"]},
    )

    assert result["ok"] is True
    payload = result["payload"]
    assert isinstance(payload["combat_result"], dict)
    assert payload["combat_result"].get("outcome") in ("hit", "miss", "crit", "graze", None)