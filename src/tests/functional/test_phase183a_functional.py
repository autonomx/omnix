"""Phase 18.3A — Functional tests for end-to-end flows."""
import importlib.util
import os
import sys
import pytest

_SRC = os.path.join(os.path.dirname(__file__), "..", "..")

def _load(name, rel_path):
    path = os.path.normpath(os.path.join(_SRC, rel_path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_prog = _load("f_prog", "app/rpg/player/player_progression_state.py")
_creation = _load("f_creation", "app/rpg/player/player_creation.py")
_ar = _load("f_ar", "app/rpg/action_resolver.py")
_xp = _load("f_xp", "app/rpg/player/player_xp_rules.py")
_wi = _load("f_wi", "app/rpg/items/world_items.py")
_inv = _load("f_inv", "app/rpg/items/inventory_state.py")
_we = _load("f_we", "app/rpg/creator/world_expansion.py")
_mi = _load("f_mi", "app/rpg/presentation/memory_inspector.py")
_sc = _load("f_sc", "app/rpg/presentation/speaker_cards.py")


class TestCharacterCreationToXpFlow:
    """Test full flow: create character -> perform action -> earn XP -> level up."""

    def test_full_progression_flow(self):
        # Step 1: Create character
        ps = _creation.apply_character_creation({}, {
            "name": "Test Hero",
            "class_id": "warrior",
            "stat_allocation": {"strength": 4, "dexterity": 3, "constitution": 3, "intelligence": 1, "wisdom": 1}
        })
        assert ps["name"] == "Test Hero"
        assert ps["stats"]["strength"] == 9

        # Step 2: Resolve combat action
        sim = {"player_state": ps}
        action = {"action_type": "attack_melee", "target": {"stats": {"dexterity": 10, "constitution": 10}, "hp": 20}}
        result = _ar.resolve_player_action(sim, action, seed=42)
        action_result = result["result"]

        # Step 3: Compute and award XP
        skill_xp = _xp.compute_action_skill_xp(action_result)
        enemy_xp = _xp.compute_enemy_difficulty_xp({"difficulty_tier": 1})
        ps = _prog.award_player_xp(ps, enemy_xp, "combat")
        for skill_id, amount in skill_xp.items():
            ps = _prog.award_skill_xp(ps, skill_id, amount, "combat_use")

        assert ps["xp"] > 0

        # Step 4: Level up
        ps["xp"] = 200  # force enough xp
        ps = _prog.resolve_level_ups(ps)
        assert ps["level"] >= 2

    def test_item_pickup_and_equip_flow(self):
        # Spawn item in world
        sim = _wi.ensure_world_item_state({})
        sim = _wi.spawn_world_item(sim, "loc:dungeon", {"item_id": "iron_sword", "name": "Iron Sword", "equipment": {"slot": "main_hand"}})

        # Pick it up
        items = _wi.list_scene_items(sim, "loc:dungeon")
        assert len(items) == 1
        instance_id = items[0]["instance_id"]
        sim = _wi.pickup_world_item(sim, instance_id)
        picked = sim["_picked_up_item"]
        assert picked["item_id"] == "iron_sword"

        # Add to inventory
        inv = _inv.normalize_inventory_state({"items": []})
        inv = _inv.add_inventory_items(inv, [picked])
        assert any(i["item_id"] == "iron_sword" for i in inv["items"])

        # Equip it
        inv = _inv.equip_inventory_item(inv, "iron_sword")
        weapon = _inv.get_equipped_weapon(inv)
        assert weapon["item_id"] == "iron_sword"

    def test_world_expansion_after_events(self):
        sim = {
            "world_expansion": {
                "allow_dynamic_npc_generation": True,
                "allow_dynamic_location_generation": True,
                "world_growth_budget": 20,
                "npc_budget": 10,
                "location_budget": 8,
                "faction_budget": 4,
                "entities_spawned": 0,
            },
            "npcs": [{"name": "Initial NPC", "seed_origin": "startup"}],
        }

        # Spawn NPC
        sim = _we.maybe_spawn_dynamic_npc(sim, {"name": "Merchant", "role": "trader"})
        assert sim["_spawn_result"]["ok"]
        assert len(sim["npcs"]) == 2
        assert sim["npcs"][0]["seed_origin"] == "startup"
        assert sim["npcs"][1]["seed_origin"] == "dynamic"

        # Spawn location
        sim = _we.maybe_spawn_dynamic_location(sim, {"name": "Hidden Valley"})
        assert sim["_spawn_result"]["ok"]


class TestNearbyNpcCards:
    def test_cards_from_scene(self):
        sim = {
            "npcs": [
                {"npc_id": "npc1", "name": "Guard", "role": "guard", "faction": "city_watch"},
                {"npc_id": "npc2", "name": "Merchant", "role": "trader"},
            ],
            "player_state": {"nearby_npc_ids": ["npc1"]},
        }
        scene = {"present_npc_ids": ["npc1", "npc2"]}
        cards = _sc.build_nearby_npc_cards(sim, scene)
        assert len(cards) == 2
        assert cards[0]["npc_id"] == "npc1"
        assert cards[0]["is_present"] is True
        assert cards[0]["name"] == "Guard"


class TestMemoryCompactPanel:
    def test_memory_summary_flow(self):
        sim = {
            "actor_memory_state": {
                "npc1": [
                    {"text": "Player helped the merchant", "strength": 0.9},
                    {"text": "Player was seen near the docks", "strength": 0.4},
                ]
            },
            "world_memory_state": {
                "rumors": [
                    {"text": "War is brewing in the north", "strength": 0.8},
                ]
            },
            "player_state": {
                "progression_log": [
                    {"type": "xp_award", "source": "combat", "amount": 35},
                ]
            },
        }
        summary = _mi.build_memory_ui_summary(sim)
        assert len(summary["important_memory"]) >= 1
        assert summary["total_memories"] >= 2
        assert len(summary["recent_world_events"]) >= 1
