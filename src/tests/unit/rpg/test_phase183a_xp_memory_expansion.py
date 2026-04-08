"""Phase 18.3A — Unit tests for XP rules, memory UI, and world expansion."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.rpg.creator.startup_pipeline import add_world_expansion_caps, mark_seed_origins
from app.rpg.creator.world_expansion import (
    maybe_spawn_dynamic_faction,
    maybe_spawn_dynamic_location,
    maybe_spawn_dynamic_npc,
)
from app.rpg.player.player_xp_rules import (
    compute_action_skill_xp,
    compute_enemy_difficulty_xp,
    compute_quest_xp,
    compute_stat_influence_bonus,
)
from app.rpg.presentation.memory_inspector import build_memory_ui_summary


class TestXpRules:
    def test_enemy_difficulty_xp(self):
        xp = compute_enemy_difficulty_xp({"difficulty_tier": 1})
        assert xp == 35  # 20 + 1*15

    def test_enemy_difficulty_xp_tier_0(self):
        xp = compute_enemy_difficulty_xp({"difficulty_tier": 0})
        assert xp == 20

    def test_quest_xp(self):
        xp = compute_quest_xp({"quest_rank": 2})
        assert xp == 100  # 50 + 2*25

    def test_action_skill_xp_success(self):
        result = compute_action_skill_xp({"skill_id": "swordsmanship", "outcome": "success", "difficulty": "normal"})
        assert "swordsmanship" in result
        assert result["swordsmanship"] > 0

    def test_action_skill_xp_failure(self):
        result = compute_action_skill_xp({"skill_id": "archery", "outcome": "failure", "difficulty": "normal"})
        assert "archery" in result
        assert result["archery"] >= 2

    def test_action_skill_xp_no_skill(self):
        result = compute_action_skill_xp({"outcome": "success"})
        assert result == {}

    def test_stat_influence_bonus(self):
        ps = {"stats": {"intelligence": 16}}
        bonus = compute_stat_influence_bonus(ps, {"stat_used": "intelligence"})
        assert bonus >= 1

    def test_stat_influence_low(self):
        ps = {"stats": {"strength": 8}}
        bonus = compute_stat_influence_bonus(ps, {"stat_used": "strength"})
        assert bonus == 0


class TestMemoryUISummary:
    def test_empty_state(self):
        result = build_memory_ui_summary({})
        assert "important_memory" in result
        assert "recent_memory" in result
        assert "recent_world_events" in result
        assert result["total_memories"] == 0

    def test_deduplication(self):
        sim = {
            "actor_memory_state": {
                "npc1": [
                    {"text": "Same memory", "strength": 0.8},
                    {"text": "Same memory", "strength": 0.7},
                    {"text": "Different memory", "strength": 0.6},
                ]
            }
        }
        result = build_memory_ui_summary(sim)
        texts = [m["text"] for m in result["expanded"]]
        assert texts.count("Same memory") == 1

    def test_important_memory_high_strength(self):
        sim = {
            "actor_memory_state": {
                "npc1": [
                    {"text": "Very important", "strength": 0.9},
                    {"text": "Less important", "strength": 0.3},
                ]
            }
        }
        result = build_memory_ui_summary(sim)
        assert len(result["important_memory"]) >= 1
        assert result["important_memory"][0]["text"] == "Very important"

    def test_recent_memory_limited(self):
        sim = {
            "actor_memory_state": {
                "npc1": [{"text": f"Memory {i}", "strength": 0.5} for i in range(20)]
            }
        }
        result = build_memory_ui_summary(sim)
        assert len(result["recent_memory"]) <= 5


class TestWorldExpansion:
    def test_spawn_dynamic_npc(self):
        sim = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim = maybe_spawn_dynamic_npc(sim, {"name": "New NPC", "role": "merchant"})
        assert sim["_spawn_result"]["ok"] is True
        assert any(n.get("name") == "New NPC" for n in sim.get("npcs", []))

    def test_npc_budget_exceeded(self):
        sim = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 0, "entities_spawned": 0, "npcs_spawned": 0}}
        sim = maybe_spawn_dynamic_npc(sim, {"name": "Test"})
        assert sim["_spawn_result"]["ok"] is False
        assert sim["_spawn_result"]["reason"] == "budget_exceeded"

    def test_npc_generation_disabled(self):
        sim = {"world_expansion": {"allow_dynamic_npc_generation": False}}
        sim = maybe_spawn_dynamic_npc(sim, {"name": "Test"})
        assert sim["_spawn_result"]["ok"] is False

    def test_spawn_dynamic_location(self):
        sim = {"world_expansion": {"allow_dynamic_location_generation": True, "world_growth_budget": 20, "location_budget": 8, "entities_spawned": 0}}
        sim = maybe_spawn_dynamic_location(sim, {"name": "Hidden Cave"})
        assert sim["_spawn_result"]["ok"] is True

    def test_spawn_dynamic_faction(self):
        sim = {"world_expansion": {"allow_dynamic_faction_generation": True, "world_growth_budget": 20, "faction_budget": 4, "entities_spawned": 0}}
        sim = maybe_spawn_dynamic_faction(sim, {"name": "Shadow Guild"})
        assert sim["_spawn_result"]["ok"] is True

    def test_deterministic_ids(self):
        sim1 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim2 = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 20, "npc_budget": 10, "entities_spawned": 0}}
        sim1 = maybe_spawn_dynamic_npc(sim1, {"name": "John", "role": "guard"})
        sim2 = maybe_spawn_dynamic_npc(sim2, {"name": "John", "role": "guard"})
        id1 = sim1.get("npcs", [{}])[-1].get("npc_id")
        id2 = sim2.get("npcs", [{}])[-1].get("npc_id")
        assert id1 == id2

    def test_seed_origins_preserved(self):
        data = {"npcs": [{"name": "Starting NPC"}], "factions": [{"name": "Starting Faction"}]}
        data = mark_seed_origins(data)
        assert data["npcs"][0]["seed_origin"] == "startup"
        assert data["factions"][0]["seed_origin"] == "startup"

    def test_expansion_caps_added(self):
        data = add_world_expansion_caps({})
        assert "world_expansion" in data
        assert data["world_expansion"]["world_growth_budget"] == 20

    def test_total_budget_enforcement(self):
        sim = {"world_expansion": {"allow_dynamic_npc_generation": True, "world_growth_budget": 1, "npc_budget": 10, "entities_spawned": 1}}
        sim = maybe_spawn_dynamic_npc(sim, {"name": "Over budget"})
        assert sim["_spawn_result"]["ok"] is False
