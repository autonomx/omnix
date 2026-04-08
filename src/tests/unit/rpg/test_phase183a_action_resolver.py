"""Phase 18.3A — Unit tests for action resolver combat."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.rpg.action_resolver import (
    compute_defense_rating,
    resolve_action,
    resolve_attack_roll,
    resolve_noncombat_check,
    resolve_player_action,
    select_equipped_weapon,
)


class TestResolveAttackRoll:
    def test_hit_with_seed(self):
        attacker = {"stats": {"strength": 14}, "skills": {"swordsmanship": {"level": 4}}}
        defender = {"stats": {"dexterity": 10, "constitution": 10}}
        weapon = {"combat_stats": {"attack_stat": "strength", "skill_id": "swordsmanship", "damage": 12, "accuracy": 3, "crit_chance": 5, "crit_bonus": 6, "armor_penetration": 0}, "quality": {"tier": 0}}
        result = resolve_attack_roll(attacker, defender, weapon, seed=42)
        assert result["outcome"] in ("hit", "crit", "graze", "miss")
        assert "damage" in result
        assert "attack_roll" in result

    def test_miss_possible(self):
        attacker = {"stats": {"strength": 3}, "skills": {}}
        defender = {"stats": {"dexterity": 18, "constitution": 14}, "inventory_state": {"equipment": {"chest": {"combat_stats": {"defense_bonus": 10}}}}}
        weapon = {"combat_stats": {"damage": 5, "accuracy": 0, "crit_chance": 0, "armor_penetration": 0}, "quality": {"tier": 0}}
        miss_count = sum(1 for s in range(100) if resolve_attack_roll(attacker, defender, weapon, seed=s)["outcome"] == "miss")
        assert miss_count > 0

    def test_crit_possible(self):
        attacker = {"stats": {"strength": 18}, "skills": {"swordsmanship": {"level": 10}}}
        defender = {"stats": {"dexterity": 5, "constitution": 5}}
        weapon = {"combat_stats": {"attack_stat": "strength", "skill_id": "swordsmanship", "damage": 20, "accuracy": 5, "crit_chance": 30, "crit_bonus": 10, "armor_penetration": 0}, "quality": {"tier": 2}}
        crit_count = sum(1 for s in range(100) if resolve_attack_roll(attacker, defender, weapon, seed=s)["is_crit"])
        assert crit_count > 0

    def test_weapon_damage_affects_result(self):
        attacker = {"stats": {"strength": 10}, "skills": {}}
        defender = {"stats": {"dexterity": 10, "constitution": 10}}
        weak = {"combat_stats": {"damage": 5, "accuracy": 10, "crit_chance": 0, "armor_penetration": 0}, "quality": {"tier": 0}}
        strong = {"combat_stats": {"damage": 50, "accuracy": 10, "crit_chance": 0, "armor_penetration": 0}, "quality": {"tier": 3}}
        r1 = resolve_attack_roll(attacker, defender, weak, seed=10)
        r2 = resolve_attack_roll(attacker, defender, strong, seed=10)
        if r1["outcome"] in ("hit", "crit") and r2["outcome"] in ("hit", "crit"):
            assert r2["damage"] > r1["damage"]

    def test_strength_affects_melee(self):
        weak = {"stats": {"strength": 5}, "skills": {}}
        strong = {"stats": {"strength": 18}, "skills": {}}
        defender = {"stats": {"dexterity": 8, "constitution": 8}}
        weapon = {"combat_stats": {"attack_stat": "strength", "damage": 10, "accuracy": 10, "crit_chance": 0, "armor_penetration": 0}, "quality": {"tier": 0}}
        # With high accuracy both should hit with seed=5
        r1 = resolve_attack_roll(weak, defender, weapon, seed=5)
        r2 = resolve_attack_roll(strong, defender, weapon, seed=5)
        if r1["outcome"] in ("hit", "crit") and r2["outcome"] in ("hit", "crit"):
            assert r2["damage"] >= r1["damage"]

    def test_armor_reduces_damage(self):
        attacker = {"stats": {"strength": 14}, "skills": {}}
        no_armor = {"stats": {"dexterity": 10, "constitution": 10}}
        heavy_armor = {"stats": {"dexterity": 10, "constitution": 10}, "inventory_state": {"equipment": {"chest": {"combat_stats": {"defense_bonus": 15}}}}}
        weapon = {"combat_stats": {"damage": 20, "accuracy": 10, "crit_chance": 0, "armor_penetration": 0}, "quality": {"tier": 0}}
        r1 = resolve_attack_roll(attacker, no_armor, weapon, seed=3)
        r2 = resolve_attack_roll(attacker, heavy_armor, weapon, seed=3)
        # Armor should reduce damage
        if r1["outcome"] in ("hit", "graze") and r2["outcome"] in ("hit", "graze"):
            assert r2["damage"] <= r1["damage"]


class TestResolveNoncombatCheck:
    def test_success(self):
        ps = {"stats": {"charisma": 16}, "skills": {"persuasion": {"level": 5}}}
        result = resolve_noncombat_check(ps, "persuade", "easy", seed=42)
        assert result["outcome"] in ("success", "critical_success", "partial", "failure")
        assert result["skill_id"] == "persuasion"

    def test_difficulty_affects_outcome(self):
        ps = {"stats": {"dexterity": 10}, "skills": {}}
        easy_success = sum(1 for s in range(50) if resolve_noncombat_check(ps, "sneak", "easy", seed=s)["outcome"] in ("success", "critical_success"))
        hard_success = sum(1 for s in range(50) if resolve_noncombat_check(ps, "sneak", "very_hard", seed=s)["outcome"] in ("success", "critical_success"))
        assert easy_success >= hard_success

    def test_hack_uses_intelligence(self):
        ps = {"stats": {"intelligence": 16}, "skills": {"hacking": {"level": 3}}}
        result = resolve_noncombat_check(ps, "hack", "normal", seed=1)
        assert result["stat_used"] == "intelligence"
        assert result["skill_id"] == "hacking"


class TestResolvePlayerAction:
    def test_melee_attack(self):
        sim = {"player_state": {"stats": {"strength": 14}, "skills": {}, "inventory_state": {"equipment": {}}}}
        action = {"action_type": "attack_melee", "target": {"stats": {"dexterity": 10, "constitution": 10}, "hp": 20}}
        result = resolve_player_action(sim, action, seed=42)
        assert "result" in result
        assert result["result"]["action_type"] == "attack_melee"

    def test_item_action(self):
        sim = {"player_state": {"stats": {"dexterity": 10}}}
        action = {"action_type": "pickup_item", "item_id": "rusty_sword"}
        result = resolve_player_action(sim, action, seed=1)
        assert result["result"]["outcome"] == "success"

    def test_sneak_action(self):
        sim = {"player_state": {"stats": {"dexterity": 14}, "skills": {"stealth": {"level": 3}}}}
        action = {"action_type": "sneak", "difficulty": "normal"}
        result = resolve_player_action(sim, action, seed=42)
        assert result["result"]["skill_id"] == "stealth"


class TestComputeDefenseRating:
    def test_no_armor(self):
        actor = {"stats": {"constitution": 10}}
        assert compute_defense_rating(actor) == 0

    def test_with_armor(self):
        actor = {"stats": {"constitution": 14}, "inventory_state": {"equipment": {"chest": {"combat_stats": {"defense_bonus": 5}}}}}
        rating = compute_defense_rating(actor)
        assert rating >= 5

    def test_high_con_adds_defense(self):
        low = compute_defense_rating({"stats": {"constitution": 8}})
        high = compute_defense_rating({"stats": {"constitution": 18}})
        assert high > low


class TestSelectEquippedWeapon:
    def test_unarmed_fallback(self):
        w = select_equipped_weapon({})
        assert w["item_id"] == "unarmed"

    def test_equipped_weapon(self):
        ps = {"inventory_state": {"equipment": {"main_hand": {"item_id": "iron_sword", "combat_stats": {"damage": 28}}}}}
        w = select_equipped_weapon(ps)
        assert w["item_id"] == "iron_sword"


class TestLegacyResolveAction:
    def test_dict_player(self):
        ps = {"stats": {"strength": 14}, "skills": {}}
        result = resolve_action(ps, "attack", "normal", seed=42)
        assert "type" in result
        assert "result" in result
        assert "damage" in result
