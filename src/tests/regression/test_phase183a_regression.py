"""Phase 18.3A — Regression tests ensuring no breakage."""
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

_prog = _load("r_prog", "app/rpg/player/player_progression_state.py")
_ar = _load("r_ar", "app/rpg/action_resolver.py")
_inv = _load("r_inv", "app/rpg/items/inventory_state.py")
_ir = _load("r_ir", "app/rpg/items/item_registry.py")
_wi = _load("r_wi", "app/rpg/items/world_items.py")
_is = _load("r_is", "app/rpg/items/item_stats.py")
_we = _load("r_we", "app/rpg/creator/world_expansion.py")


class TestLegacyCompatibility:
    """Ensure Phase 18.3A doesn't break existing functionality."""

    def test_old_item_registry_items_still_exist(self):
        """Original items should still be accessible."""
        for item_id in ["gold_coin", "healing_potion", "bandit_token"]:
            item = _ir.get_item_definition(item_id)
            assert item, f"Legacy item missing: {item_id}"

    def test_normalize_inventory_backward_compat(self):
        """Old inventory format should still normalize correctly."""
        inv = _inv.normalize_inventory_state({
            "items": [{"item_id": "healing_potion", "qty": 3}],
            "equipment": {},
            "capacity": 50,
        })
        assert len(inv["items"]) == 1
        assert inv["items"][0]["qty"] == 3

    def test_legacy_resolve_action(self):
        """Old resolve_action signature should still work with dict."""
        ps = {"stats": {"strength": 12}, "skills": {"swordsmanship": 3}}
        result = _ar.resolve_action(ps, "attack", "normal", seed=42)
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
        ps = _prog.ensure_player_progression_state(existing)
        assert ps["name"] == "ExistingPlayer"
        assert ps["level"] == 5
        assert ps["custom_field"] == "preserved"


class TestDeterminism:
    """Ensure all operations are deterministic with same seed."""

    def test_attack_deterministic(self):
        attacker = {"stats": {"strength": 14}, "skills": {}}
        defender = {"stats": {"dexterity": 10, "constitution": 10}}
        weapon = {"combat_stats": {"damage": 12, "accuracy": 3, "crit_chance": 5, "crit_bonus": 6, "armor_penetration": 0}, "quality": {"tier": 0}}
        r1 = _ar.resolve_attack_roll(attacker, defender, weapon, seed=99)
        r2 = _ar.resolve_attack_roll(attacker, defender, weapon, seed=99)
        assert r1 == r2

    def test_noncombat_deterministic(self):
        ps = {"stats": {"charisma": 14}, "skills": {}}
        r1 = _ar.resolve_noncombat_check(ps, "persuade", "normal", seed=77)
        r2 = _ar.resolve_noncombat_check(ps, "persuade", "normal", seed=77)
        assert r1 == r2

    def test_expansion_ids_deterministic(self):
        sim1 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim2 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim1 = _we.maybe_spawn_dynamic_npc(sim1, {"name": "TestNPC", "role": "guard"})
        sim2 = _we.maybe_spawn_dynamic_npc(sim2, {"name": "TestNPC", "role": "guard"})
        assert sim1["npcs"][-1]["npc_id"] == sim2["npcs"][-1]["npc_id"]


class TestBoundedState:
    """Ensure all state is bounded and safe."""

    def test_progression_log_bounded(self):
        ps = _prog.ensure_player_progression_state({"progression_log": [{"type": f"test_{i}"} for i in range(200)]})
        assert len(ps["progression_log"]) <= 50

    def test_inventory_capacity_bounded(self):
        inv = _inv.normalize_inventory_state({"items": [{"item_id": f"item_{i}", "qty": 1} for i in range(100)]})
        assert len(inv["items"]) <= 50

    def test_stat_allocation_bounded(self):
        ps = _prog.allocate_starting_stats({}, {"strength": 999})
        assert ps["stats"]["strength"] <= 20

    def test_generated_item_clamped(self):
        gib = _load("r_gib", "app/rpg/items/generated_item_builder.py")
        item = gib.clamp_generated_item_stats({"combat_stats": {"damage": 9999}, "quality": {"rarity": "common"}}, world_tier=0)
        assert item["combat_stats"]["damage"] <= 20

    def test_world_items_idempotent(self):
        sim = _wi.ensure_world_item_state({})
        sim2 = _wi.ensure_world_item_state(sim)
        assert sim["world_items"] == sim2["world_items"]


class TestNoBrokenImports:
    """Verify all new modules can be loaded without error."""

    def test_load_player_progression(self):
        mod = _load("test_imp_prog", "app/rpg/player/player_progression_state.py")
        assert hasattr(mod, "ensure_player_progression_state")

    def test_load_player_creation(self):
        mod = _load("test_imp_creation", "app/rpg/player/player_creation.py")
        assert hasattr(mod, "apply_character_creation")

    def test_load_item_stats(self):
        mod = _load("test_imp_is", "app/rpg/items/item_stats.py")
        assert hasattr(mod, "normalize_item_stats")

    def test_load_world_items(self):
        mod = _load("test_imp_wi", "app/rpg/items/world_items.py")
        assert hasattr(mod, "ensure_world_item_state")

    def test_load_generated_item_builder(self):
        mod = _load("test_imp_gib", "app/rpg/items/generated_item_builder.py")
        assert hasattr(mod, "build_item_definition_from_llm")

    def test_load_xp_rules(self):
        mod = _load("test_imp_xp", "app/rpg/player/player_xp_rules.py")
        assert hasattr(mod, "compute_enemy_difficulty_xp")

    def test_load_world_expansion(self):
        mod = _load("test_imp_we", "app/rpg/creator/world_expansion.py")
        assert hasattr(mod, "maybe_spawn_dynamic_npc")
