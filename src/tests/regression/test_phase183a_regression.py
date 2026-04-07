"""Phase 18.3A — Regression tests ensuring no breakage."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from app.rpg.player.player_progression_state import (
    ensure_player_progression_state,
    allocate_starting_stats,
)
from app.rpg.action_resolver import (
    resolve_attack_roll,
    resolve_noncombat_check,
    resolve_action,
)
from app.rpg.items.inventory_state import normalize_inventory_state
from app.rpg.items.item_registry import get_item_definition
from app.rpg.items.world_items import ensure_world_item_state
from app.rpg.items.item_stats import normalize_item_stats
from app.rpg.creator.world_expansion import maybe_spawn_dynamic_npc
from app.rpg.items.generated_item_builder import clamp_generated_item_stats


class TestLegacyCompatibility:
    """Ensure Phase 18.3A doesn't break existing functionality."""

    def test_old_item_registry_items_still_exist(self):
        """Original items should still be accessible."""
        for item_id in ["gold_coin", "healing_potion", "bandit_token"]:
            item = get_item_definition(item_id)
            assert item, f"Legacy item missing: {item_id}"

    def test_normalize_inventory_backward_compat(self):
        """Old inventory format should still normalize correctly."""
        inv = normalize_inventory_state({
            "items": [{"item_id": "healing_potion", "qty": 3}],
            "equipment": {},
            "capacity": 50,
        })
        assert len(inv["items"]) == 1
        assert inv["items"][0]["qty"] == 3

    def test_legacy_resolve_action(self):
        """Old resolve_action signature should still work with dict."""
        ps = {"stats": {"strength": 12}, "skills": {"swordsmanship": 3}}
        result = resolve_action(ps, "attack", "normal", seed=42)
        assert "type" in result
        assert "damage" in result
        assert result["type"] == "attack"

    def test_player_state_backward_compat(self):
        """ensure_player_progression_state should not corrupt existing state."""
        existing = {
            "name": "ExistingPlayer",
            "level": 5,
            "xp": 250,
            "custom_field": "preserved",
        }
        ps = ensure_player_progression_state(existing)
        assert ps["name"] == "ExistingPlayer"
        assert ps["level"] == 5
        assert ps["custom_field"] == "preserved"


class TestDeterminism:
    """Ensure all operations are deterministic with same seed."""

    def test_attack_deterministic(self):
        attacker = {"stats": {"strength": 14}, "skills": {}}
        defender = {"stats": {"dexterity": 10, "constitution": 10}}
        weapon = {"combat_stats": {"damage": 12, "accuracy": 3, "crit_chance": 5, "crit_bonus": 6, "armor_penetration": 0}, "quality": {"tier": 0}}
        r1 = resolve_attack_roll(attacker, defender, weapon, seed=99)
        r2 = resolve_attack_roll(attacker, defender, weapon, seed=99)
        assert r1 == r2

    def test_noncombat_deterministic(self):
        ps = {"stats": {"charisma": 14}, "skills": {}}
        r1 = resolve_noncombat_check(ps, "persuade", "normal", seed=77)
        r2 = resolve_noncombat_check(ps, "persuade", "normal", seed=77)
        assert r1 == r2

    def test_expansion_ids_deterministic(self):
        sim1 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim2 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim1 = maybe_spawn_dynamic_npc(sim1, {"name": "TestNPC", "role": "guard"})
        sim2 = maybe_spawn_dynamic_npc(sim2, {"name": "TestNPC", "role": "guard"})
        assert sim1["npcs"][-1]["npc_id"] == sim2["npcs"][-1]["npc_id"]


class TestBoundedState:
    """Ensure all state is bounded and safe."""

    def test_progression_log_bounded(self):
        ps = ensure_player_progression_state({"progression_log": [{"type": f"test_{i}"} for i in range(200)]})
        assert len(ps["progression_log"]) <= 50

    def test_inventory_capacity_bounded(self):
        inv = normalize_inventory_state({"items": [{"item_id": f"item_{i}", "qty": 1} for i in range(100)]})
        assert len(inv["items"]) <= 50

    def test_stat_allocation_bounded(self):
        ps = allocate_starting_stats({}, {"strength": 999})
        assert ps["stats"]["strength"] <= 20

    def test_generated_item_clamped(self):
        item = clamp_generated_item_stats({"combat_stats": {"damage": 9999}, "quality": {"rarity": "common"}}, world_tier=0)
        assert item["combat_stats"]["damage"] <= 20

    def test_world_items_idempotent(self):
        sim = ensure_world_item_state({})
        sim2 = ensure_world_item_state(sim)
        assert sim["world_items"] == sim2["world_items"]


class TestNoBrokenImports:
    """Verify all new modules can be loaded without error."""

    def test_load_player_progression(self):
        from app.rpg.player.player_progression_state import ensure_player_progression_state as fn
        assert fn is not None

    def test_load_player_creation(self):
        from app.rpg.player.player_creation import apply_character_creation as fn
        assert fn is not None

    def test_load_item_stats(self):
        from app.rpg.items.item_stats import normalize_item_stats as fn
        assert fn is not None

    def test_load_world_items(self):
        from app.rpg.items.world_items import ensure_world_item_state as fn
        assert fn is not None

    def test_load_generated_item_builder(self):
        from app.rpg.items.generated_item_builder import build_item_definition_from_llm as fn
        assert fn is not None

    def test_load_xp_rules(self):
        from app.rpg.player.player_xp_rules import compute_enemy_difficulty_xp as fn
        assert fn is not None

    def test_load_world_expansion(self):
        from app.rpg.creator.world_expansion import maybe_spawn_dynamic_npc as fn
        assert fn is not None
