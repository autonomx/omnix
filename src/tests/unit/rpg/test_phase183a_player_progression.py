"""Phase 18.3A — Unit tests for player progression state."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.rpg.player.player_creation import (
    apply_character_creation,
    build_default_stat_allocation,
    validate_stat_allocation,
)
from app.rpg.player.player_progression_state import (
    allocate_starting_stats,
    award_player_xp,
    award_skill_xp,
    ensure_player_progression_state,
    get_skill_level,
    get_stat_modifier,
    resolve_level_ups,
    resolve_skill_level_ups,
)


class TestEnsurePlayerProgressionState:
    def test_creates_defaults(self):
        ps = ensure_player_progression_state({})
        assert ps["level"] == 1
        assert ps["xp"] == 0
        assert ps["xp_to_next"] == 100
        assert "strength" in ps["stats"]
        assert "swordsmanship" in ps["skills"]
        assert ps["name"] == "Player"

    def test_idempotent(self):
        ps = ensure_player_progression_state({})
        ps2 = ensure_player_progression_state(ps)
        assert ps == ps2

    def test_preserves_existing(self):
        ps = ensure_player_progression_state({"name": "Hero", "level": 5})
        assert ps["name"] == "Hero"
        assert ps["level"] == 5

    def test_progression_log_bounded(self):
        ps = {"progression_log": [{"type": "test"}] * 100}
        ps = ensure_player_progression_state(ps)
        assert len(ps["progression_log"]) <= 50

    def test_all_default_stats_present(self):
        ps = ensure_player_progression_state({})
        for stat in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            assert stat in ps["stats"]
            assert ps["stats"][stat] == 5

    def test_all_default_skills_present(self):
        ps = ensure_player_progression_state({})
        for skill in ["swordsmanship", "archery", "firearms", "defense", "stealth", "persuasion", "intimidation", "investigation", "magic", "hacking"]:
            assert skill in ps["skills"]
            assert ps["skills"][skill]["level"] == 0


class TestAllocateStartingStats:
    def test_allocate(self):
        ps = allocate_starting_stats({}, {"strength": 3, "dexterity": 2})
        assert ps["stats"]["strength"] == 8
        assert ps["stats"]["dexterity"] == 7

    def test_clamped_max_20(self):
        ps = allocate_starting_stats({"stats": {"strength": 19}}, {"strength": 5})
        assert ps["stats"]["strength"] == 20

    def test_clamped_min_1(self):
        ps = allocate_starting_stats({}, {"strength": -100})
        assert ps["stats"]["strength"] >= 1

    def test_unknown_stat_ignored(self):
        ps = allocate_starting_stats({}, {"unknown_stat": 5})
        assert "unknown_stat" not in ps["stats"]


class TestGetStatModifier:
    def test_modifier_10(self):
        assert get_stat_modifier(10) == 0

    def test_modifier_14(self):
        assert get_stat_modifier(14) == 2

    def test_modifier_8(self):
        assert get_stat_modifier(8) == -1

    def test_modifier_5(self):
        assert get_stat_modifier(5) == -3  # (5-10)//2 = -3 (floor division)


class TestGetSkillLevel:
    def test_existing_skill(self):
        ps = ensure_player_progression_state({})
        ps["skills"]["swordsmanship"]["level"] = 3
        assert get_skill_level(ps, "swordsmanship") == 3

    def test_missing_skill(self):
        ps = ensure_player_progression_state({})
        assert get_skill_level(ps, "nonexistent") == 0


class TestAwardPlayerXp:
    def test_awards_xp(self):
        ps = award_player_xp({}, 50, "combat")
        assert ps["xp"] == 50

    def test_logs_award(self):
        ps = award_player_xp({}, 25, "quest")
        assert any(e["type"] == "xp_award" for e in ps["progression_log"])

    def test_negative_clamped(self):
        ps = award_player_xp({}, -10, "test")
        assert ps["xp"] == 0


class TestAwardSkillXp:
    def test_awards_skill_xp(self):
        ps = award_skill_xp({}, "archery", 10, "practice")
        assert ps["skills"]["archery"]["xp"] == 10

    def test_new_skill_created(self):
        ps = award_skill_xp({}, "cooking", 5, "test")
        assert "cooking" in ps["skills"]
        assert ps["skills"]["cooking"]["xp"] == 5


class TestResolveLevelUps:
    def test_level_up(self):
        ps = ensure_player_progression_state({"xp": 150})
        ps = resolve_level_ups(ps)
        assert ps["level"] == 2
        assert ps["unspent_points"] == 2

    def test_multiple_level_ups(self):
        ps = ensure_player_progression_state({"xp": 500})
        ps = resolve_level_ups(ps)
        assert ps["level"] > 2

    def test_no_level_up_below_threshold(self):
        ps = ensure_player_progression_state({"xp": 50})
        ps = resolve_level_ups(ps)
        assert ps["level"] == 1

    def test_xp_remainder_preserved(self):
        ps = ensure_player_progression_state({"xp": 120})
        ps = resolve_level_ups(ps)
        assert ps["xp"] == 20  # 120 - 100


class TestResolveSkillLevelUps:
    def test_skill_level_up(self):
        ps = ensure_player_progression_state({})
        ps["skills"]["archery"]["xp"] = 30
        ps = resolve_skill_level_ups(ps)
        assert ps["skills"]["archery"]["level"] == 1

    def test_multiple_skill_level_ups(self):
        ps = ensure_player_progression_state({})
        ps["skills"]["stealth"]["xp"] = 100
        ps = resolve_skill_level_ups(ps)
        assert ps["skills"]["stealth"]["level"] >= 2


class TestCharacterCreation:
    def test_build_default_allocation(self):
        alloc = build_default_stat_allocation()
        assert sum(alloc.values()) == 12

    def test_validate_allocation_valid(self):
        result = validate_stat_allocation({"strength": 4, "dexterity": 4, "constitution": 4})
        assert result["ok"] is True

    def test_validate_allocation_over_budget(self):
        result = validate_stat_allocation({"strength": 10, "dexterity": 10})
        assert result["ok"] is False

    def test_validate_allocation_unknown_stat(self):
        result = validate_stat_allocation({"flying": 5})
        assert result["ok"] is False

    def test_apply_character_creation(self):
        ps = apply_character_creation({}, {"name": "Gandalf", "class_id": "mage", "stat_allocation": {"intelligence": 4, "wisdom": 4, "charisma": 4}})
        assert ps["name"] == "Gandalf"
        assert ps["class_id"] == "mage"
        assert ps["stats"]["intelligence"] == 9  # 5 + 4

    def test_invalid_allocation_not_applied(self):
        ps = apply_character_creation({}, {"stat_allocation": {"strength": 100}})
        assert ps["stats"]["strength"] == 5  # unchanged, over budget
