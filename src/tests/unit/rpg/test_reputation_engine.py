"""Tests for TIER 7: Reputation Engine.

Tests the ReputationEngine and FactionStanding classes from
src/app/rpg/world/reputation_engine.py.

Test Coverage:
- Reputation changes via apply_action
- Attitude classification (hostile, unfriendly, neutral, friendly, ally)
- Reputation locking/unlocking
- Decay toward neutral
- History tracking
- Top/bottom faction queries
"""

import os
import sys

import pytest

# Add app directory to path (same as test_tier6_narrative_intelligence.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.world.reputation_engine import (
    ReputationEngine,
    FactionStanding,
    ATTITUDE_HOSTILE_THRESHOLD,
    ATTITUDE_FRIENDLY_THRESHOLD,
    ATTITUDE_ALLY_THRESHOLD,
    MAX_REPUTATION,
    MIN_REPUTATION,
)


class TestFactionStanding:
    """Test FactionStanding model."""

    def test_faction_standing_defaults(self):
        """Test default standing values."""
        standing = FactionStanding()
        
        assert standing.reputation == 0.0
        assert standing.history == []
        assert standing.last_change_tick == -1
        assert standing.locked is False

    def test_faction_standing_to_dict(self):
        """Test serialization to dict."""
        standing = FactionStanding(
            reputation=0.5,
            history=[("help", 0.3, 1)],
            last_change_tick=5,
            locked=True,
        )
        
        data = standing.to_dict()
        
        assert data["reputation"] == 0.5
        assert data["history_length"] == 1
        assert data["last_change_tick"] == 5
        assert data["locked"] is True


class TestReputationEngine:
    """Test ReputationEngine."""

    def test_initial_reputation_is_zero(self):
        """Test that unknown factions have zero reputation."""
        rep = ReputationEngine()
        
        assert rep.get("unknown_faction") == 0.0

    def test_apply_action_increases_reputation(self):
        """Test that positive delta increases reputation."""
        rep = ReputationEngine()
        
        rep.apply_action("help_mage", {"faction_rep": {"mages_guild": 0.3}}, tick=1)
        
        assert rep.get("mages_guild") == 0.3

    def test_apply_action_decreases_reputation(self):
        """Test that negative delta decreases reputation."""
        rep = ReputationEngine()
        
        rep.apply_action("attack_mage", {"faction_rep": {"mages_guild": -0.4}}, tick=1)
        
        assert rep.get("mages_guild") == -0.4

    def test_apply_action_multiple_factions(self):
        """Test updating multiple factions at once."""
        rep = ReputationEngine()
        
        effects = {
            "faction_rep": {
                "mages_guild": 0.3,
                "warriors_guild": -0.2,
                "thieves_guild": 0.1,
            }
        }
        rep.apply_action("some_action", effects, tick=1)
        
        assert rep.get("mages_guild") == 0.3
        assert rep.get("warriors_guild") == -0.2
        assert rep.get("thieves_guild") == 0.1

    def test_apply_action_clamps_to_valid_range(self):
        """Test that reputation is clamped to -1.0 to 1.0."""
        rep = ReputationEngine()
        rep.set("test", 0.8)
        
        # Large positive delta
        rep.apply_action("big_help", {"faction_rep": {"test": 0.5}}, tick=1)
        assert rep.get("test") == 1.0
        
        # Large negative delta from start
        rep2 = ReputationEngine()
        rep2.set("test2", -0.8)
        rep2.apply_action("big_attack", {"faction_rep": {"test2": -0.5}}, tick=1)
        assert rep2.get("test2") == -1.0

    def test_apply_action_records_history(self):
        """Test that history is recorded."""
        rep = ReputationEngine()
        
        rep.apply_action("help_mage", {"faction_rep": {"mages_guild": 0.3}}, tick=1)
        rep.apply_action("help_mage_again", {"faction_rep": {"mages_guild": 0.2}}, tick=2)
        
        history = rep.get_history("mages_guild")
        
        assert len(history) == 2
        assert history[0] == ("help_mage", 0.3, 1)
        assert history[1] == ("help_mage_again", 0.2, 2)

    def test_apply_action_skips_locked_factions(self):
        """Test that locked factions cannot have reputation changed."""
        rep = ReputationEngine()
        
        rep.set("locked_faction", 0.5)
        rep.lock("locked_faction")
        
        changes = rep.apply_action("help", {"faction_rep": {"locked_faction": 0.3}}, tick=1)
        
        assert "locked_faction" not in changes
        assert rep.get("locked_faction") == 0.5

    def test_apply_action_invalid_faction_rep_type(self):
        """Test that non-dict faction_rep is ignored."""
        rep = ReputationEngine()
        
        changes = rep.apply_action("test", {"faction_rep": "invalid"}, tick=1)
        
        assert changes == {}

    def test_apply_action_non_number_delta_ignored(self):
        """Test that non-number deltas are ignored."""
        rep = ReputationEngine()
        
        changes = rep.apply_action("test", {"faction_rep": {"guild": "abc"}}, tick=1)
        
        assert changes == {}

    def test_set_direct_reputation(self):
        """Test directly setting reputation."""
        rep = ReputationEngine()
        
        rep.set("guild", 0.8)
        assert rep.get("guild") == 0.8
        
        rep.set("guild", -0.5)
        assert rep.get("guild") == -0.5

    def test_set_clamps_to_valid_range(self):
        """Test that set clamps to -1.0 to 1.0."""
        rep = ReputationEngine()
        
        rep.set("guild", 2.0)
        assert rep.get("guild") == 1.0
        
        rep.set("guild", -2.0)
        assert rep.get("guild") == -1.0


class TestAttitudeClassification:
    """Test attitude classification based on reputation thresholds."""

    def test_hostile_attitude(self):
        """Test reputation below hostile threshold."""
        rep = ReputationEngine()
        rep.set("guild", ATTITUDE_HOSTILE_THRESHOLD - 0.1)
        
        assert rep.get_attitude("guild") == "hostile"

    def test_unfriendly_attitude(self):
        """Test reputation between hostile and 0."""
        rep = ReputationEngine()
        rep.set("guild", -0.3)
        
        assert rep.get_attitude("guild") == "unfriendly"

    def test_neutral_attitude(self):
        """Test reputation between 0 and friendly threshold."""
        rep = ReputationEngine()
        rep.set("guild", 0.1)
        
        assert rep.get_attitude("guild") == "neutral"

    def test_friendly_attitude(self):
        """Test reputation between friendly and ally threshold."""
        rep = ReputationEngine()
        rep.set("guild", 0.4)
        
        assert rep.get_attitude("guild") == "friendly"

    def test_ally_attitude(self):
        """Test reputation at or above ally threshold."""
        rep = ReputationEngine()
        rep.set("guild", ATTITUDE_ALLY_THRESHOLD)
        
        assert rep.get_attitude("guild") == "ally"

    def test_unknown_faction_is_neutral(self):
        """Test that unknown factions have neutral attitude."""
        rep = ReputationEngine()
        
        # Unknown factions return 0.0 reputation, which is "neutral"
        assert rep.get_attitude("unknown") == "neutral"

    def test_boundary_values(self):
        """Test attitude at exact boundary values."""
        rep = ReputationEngine()
        
        # At exactly hostile threshold (-0.5 is not < -0.5)
        rep.set("a", ATTITUDE_HOSTILE_THRESHOLD)
        assert rep.get_attitude("a") == "unfriendly"
        
        # At exactly 0
        rep.set("b", 0.0)
        assert rep.get_attitude("b") == "neutral"
        
        # At exactly friendly threshold
        rep.set("c", ATTITUDE_FRIENDLY_THRESHOLD)
        assert rep.get_attitude("c") == "friendly"
        
        # At exactly ally threshold
        rep.set("d", ATTITUDE_ALLY_THRESHOLD)
        assert rep.get_attitude("d") == "ally"


class TestReputationLocking:
    """Test reputation locking functionality."""

    def test_lock_prevents_changes(self):
        """Test that locked factions cannot have reputation changed."""
        rep = ReputationEngine()
        rep.set("guild", 0.5)
        rep.lock("guild")
        
        # Via apply_action
        rep.apply_action("help", {"faction_rep": {"guild": 0.3}}, tick=1)
        assert rep.get("guild") == 0.5
        
        # Via set
        standing = rep.reputation["guild"]
        standing.locked = True
        
    def test_unlock_allows_changes(self):
        """Test that unlocked factions can have reputation changed."""
        rep = ReputationEngine()
        rep.set("guild", 0.5)
        rep.lock("guild")
        rep.unlock("guild")
        
        rep.apply_action("help", {"faction_rep": {"guild": 0.3}}, tick=1)
        assert rep.get("guild") == 0.8

    def test_lock_creates_standing(self):
        """Test that locking creates standing if not exists."""
        rep = ReputationEngine()
        rep.lock("guild")
        
        assert "guild" in rep.reputation


class TestReputationDecay:
    """Test reputation decay toward neutral."""

    def test_decay_positive_reputation(self):
        """Test that positive reputation decays toward zero."""
        rep = ReputationEngine(decay_rate=0.1)
        rep.set("guild", 0.5)
        
        changes = rep.decay(tick=1)
        
        assert "guild" in changes
        assert changes["guild"] < 0.5
        assert changes["guild"] >= 0.0

    def test_decay_negative_reputation(self):
        """Test that negative reputation decays toward zero."""
        rep = ReputationEngine(decay_rate=0.1)
        rep.set("guild", -0.5)
        
        changes = rep.decay(tick=1)
        
        assert "guild" in changes
        assert changes["guild"] > -0.5
        assert changes["guild"] <= 0.0

    def test_decay_locked_factions_ignored(self):
        """Test that locked factions don't decay."""
        rep = ReputationEngine(decay_rate=0.1)
        rep.set("guild", 0.8)
        rep.lock("guild")
        
        changes = rep.decay(tick=1)
        
        assert "guild" not in changes
        assert rep.get("guild") == 0.8

    def test_decay_disabled_when_rate_zero(self):
        """Test that decay_rate=0 disables decay."""
        rep = ReputationEngine(decay_rate=0.0)
        rep.set("guild", 0.8)
        
        changes = rep.decay(tick=1)
        
        assert changes == {}

    def test_decay_near_zero_skips(self):
        """Test that reputation near zero doesn't decay."""
        rep = ReputationEngine(decay_rate=0.1)
        rep.set("guild", 0.005)  # Very small
        
        changes = rep.decay(tick=1)
        
        # Should skip since abs(0.005) < 0.01
        assert "guild" not in changes


class TestReputationQueries:
    """Test reputation query methods."""

    def test_get_top_factions(self):
        """Test getting factions with highest reputation."""
        rep = ReputationEngine()
        rep.set("a", 0.8)
        rep.set("b", 0.3)
        rep.set("c", 0.9)
        
        top = rep.get_top_factions(count=2)
        
        assert len(top) == 2
        assert top[0] == ("c", 0.9)
        assert top[1] == ("a", 0.8)

    def test_get_bottom_factions(self):
        """Test getting factions with lowest reputation."""
        rep = ReputationEngine()
        rep.set("a", -0.8)
        rep.set("b", -0.3)
        rep.set("c", -0.9)
        
        bottom = rep.get_bottom_factions(count=2)
        
        assert len(bottom) == 2
        assert bottom[0] == ("c", -0.9)
        assert bottom[1] == ("a", -0.8)

    def test_get_attitude_summary(self):
        """Test getting attitude summary for all factions."""
        rep = ReputationEngine()
        rep.set("ally", 0.8)
        rep.set("enemy", -0.8)
        rep.set("neutral", 0.0)  # Should be excluded
        
        summary = rep.get_attitude_summary()
        
        assert summary.get("ally") == "ally"
        assert summary.get("enemy") == "hostile"
        assert "neutral" not in summary

    def test_has_interaction_with(self):
        """Test checking if player has interacted with faction."""
        rep = ReputationEngine()
        
        assert rep.has_interaction_with("guild") is False
        
        rep.apply_action("help", {"faction_rep": {"guild": 0.3}}, tick=1)
        
        assert rep.has_interaction_with("guild") is True


class TestReputationEngineReset:
    """Test reputation engine reset."""

    def test_reset_clears_all_data(self):
        """Test that reset clears all reputation data."""
        rep = ReputationEngine()
        rep.set("guild", 0.5)
        rep.set("enemy", -0.3)
        
        rep.reset()
        
        assert rep.get("guild") == 0.  # Back to default
        assert rep.get("enemy") == 0.0
        assert len(rep.reputation) == 0


class TestReputationIntegration:
    """Test reputation integration with typical usage patterns."""

    def test_reputation_changes_affect_attitude(self):
        """Test that enough reputation changes shift attitude.
        
        This test demonstrates the key integration point:
        applying enough reputation changes should shift the 
        faction's attitude classification.
        """
        rep = ReputationEngine()
        
        # Start neutral
        assert rep.get_attitude("mages_guild") == "neutral"
        
        # Apply several positive actions
        for i in range(3):
            rep.apply_action("help_mages", {"faction_rep": {"mages_guild": 0.25}}, tick=i)
        
        # Should now be ally
        assert rep.get_attitude("mages_guild") == "ally"
        
        # Apply negative actions
        for i in range(5):
            rep.apply_action("attack_mages", {"faction_rep": {"mages_guild": -0.3}}, tick=10+i)
        
        # Should now be hostile
        assert rep.get_attitude("mages_guild") == "hostile"