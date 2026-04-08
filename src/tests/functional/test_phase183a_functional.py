"""Phase 18.3A — Functional tests for end-to-end flows."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from app.rpg.player.player_progression_state import (
    ensure_player_progression_state,
    award_player_xp,
    award_skill_xp,
    resolve_level_ups,
)
from app.rpg.player.player_creation import apply_character_creation
from app.rpg.action_resolver import resolve_player_action
from app.rpg.player.player_xp_rules import (
    compute_action_skill_xp,
    compute_enemy_difficulty_xp,
)
from app.rpg.items.world_items import (
    ensure_world_item_state,
    spawn_world_item,
    pickup_world_item,
    list_scene_items,
)
from app.rpg.items.inventory_state import (
    normalize_inventory_state,
    add_inventory_items,
    equip_inventory_item,
    get_equipped_weapon,
)
from app.rpg.creator.world_expansion import (
    maybe_spawn_dynamic_npc,
    maybe_spawn_dynamic_location,
)
from app.rpg.presentation.memory_inspector import build_memory_ui_summary
from app.rpg.presentation.speaker_cards import build_nearby_npc_cards


class TestCharacterCreationToXpFlow:
    """Test full flow: create character -> perform action -> earn XP -> level up."""

    def test_full_progression_flow(self):
        # Step 1: Create character
        ps = apply_character_creation({}, {
            "name": "Test Hero",
            "class_id": "warrior",
            "stat_allocation": {"strength": 4, "dexterity": 3, "constitution": 3, "intelligence": 1, "wisdom": 1}
        })
        assert ps["name"] == "Test Hero"
        assert ps["stats"]["strength"] == 9

        # Step 2: Resolve combat action
        sim = {"player_state": ps}
        action = {"action_type": "attack_melee", "target": {"stats": {"dexterity": 10, "constitution": 10}, "hp": 20}}
        result = resolve_player_action(sim, action, seed=42)
        action_result = result["result"]

        # Step 3: Compute and award XP
        skill_xp = compute_action_skill_xp(action_result)
        enemy_xp = compute_enemy_difficulty_xp({"difficulty_tier": 1})
        ps = award_player_xp(ps, enemy_xp, "combat")
        for skill_id, amount in skill_xp.items():
            ps = award_skill_xp(ps, skill_id, amount, "combat_use")

        assert ps["xp"] > 0

        # Step 4: Level up
        ps["xp"] = 200  # force enough xp
        ps = resolve_level_ups(ps)
        assert ps["level"] >= 2

    def test_item_pickup_and_equip_flow(self):
        # Spawn item in world
        sim = ensure_world_item_state({})
        sim = spawn_world_item(sim, "loc:dungeon", {"item_id": "iron_sword", "name": "Iron Sword", "equipment": {"slot": "main_hand"}})

        # Pick it up
        items = list_scene_items(sim, "loc:dungeon")
        assert len(items) == 1
        instance_id = items[0]["instance_id"]
        sim = pickup_world_item(sim, instance_id)
        picked = sim["_picked_up_item"]
        assert picked["item_id"] == "iron_sword"

        # Add to inventory
        inv = normalize_inventory_state({"items": []})
        inv = add_inventory_items(inv, [picked])
        assert any(i["item_id"] == "iron_sword" for i in inv["items"])

        # Equip it
        inv = equip_inventory_item(inv, "iron_sword")
        weapon = get_equipped_weapon(inv)
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
        sim = maybe_spawn_dynamic_npc(sim, {"name": "Merchant", "role": "trader"})
        assert sim["_spawn_result"]["ok"]
        assert len(sim["npcs"]) == 2
        assert sim["npcs"][0]["seed_origin"] == "startup"
        assert sim["npcs"][1]["seed_origin"] == "dynamic"

        # Spawn location
        sim = maybe_spawn_dynamic_location(sim, {"name": "Hidden Valley"})
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
        cards = build_nearby_npc_cards(sim, scene)
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
        summary = build_memory_ui_summary(sim)
        assert len(summary["important_memory"]) >= 1
        assert summary["total_memories"] >= 2
        assert len(summary["recent_world_events"]) >= 1
