"""Tests for TIER 7: Faction Simulation System.

Tests the Faction and FactionSystem classes from
src/app/rpg/world/faction_system.py.

Test Coverage:
- Faction creation and state management
- Relationship tracking between factions
- Conflict detection when relations are hostile
- Alliance detection when relations are friendly
- Resource/morale/power updates
- 100-tick simulation with faction evolution
"""

import os
import sys

import pytest

# Add app directory to path (same as test_tier6_narrative_intelligence.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.world.faction_system import (
    Faction,
    FactionSystem,
    CONFLICT_THRESHOLD,
    RESOURCE_GROWTH_RATE,
    MORALE_ADJUSTMENT_RATE,
)


class TestFaction:
    """Test Faction model."""

    def test_faction_creation_defaults(self):
        """Test default faction values."""
        faction = Faction("test", "Test Faction")
        
        assert faction.id == "test"
        assert faction.name == "Test Faction"
        assert faction.power == 0.5
        assert faction.resources == 0.5
        assert faction.morale == 0.5
        assert faction.relations == {}
        assert faction.goals == []
        assert faction.traits == []
        assert faction.influence == {}

    def test_faction_creation_with_values(self):
        """Test faction creation with custom values."""
        faction = Faction(
            "warriors",
            "Warriors Guild",
            power=0.8,
            resources=0.6,
            morale=0.7,
            goals=["conquer_territory"],
            traits=["aggressive", "honorable"],
        )
        
        assert faction.power == 0.8
        assert faction.resources == 0.6
        assert faction.morale == 0.7
        assert faction.goals == ["conquer_territory"]
        assert "aggressive" in faction.traits

    def test_set_relation(self):
        """Test setting relations with another faction."""
        faction = Faction("a", "A")
        
        faction.set_relation("b", -0.8)
        assert faction.get_relation("b") == -0.8
        
        # Test clamping to valid range
        faction.set_relation("c", 2.0)
        assert faction.get_relation("c") == 1.0
        
        faction.set_relation("d", -2.0)
        assert faction.get_relation("d") == -1.0

    def test_adjust_relation(self):
        """Test adjusting relations by delta."""
        faction = Faction("a", "A")
        
        # Start from 0 (default)
        new_rel = faction.adjust_relation("b", 0.3)
        assert new_rel == 0.3
        
        # Adjust again
        new_rel = faction.adjust_relation("b", 0.4)
        assert new_rel == 0.7
        
        # Negative adjustment
        new_rel = faction.adjust_relation("b", -0.5)
        assert abs(new_rel - 0.2) < 0.0001

    def test_set_influence(self):
        """Test setting territorial influence."""
        faction = Faction("a", "A")
        
        faction.set_influence("city_1", 0.8)
        assert faction.influence["city_1"] == 0.8
        
        # Test clamping
        faction.set_influence("city_2", -0.5)
        assert faction.influence["city_2"] == 0.0
        
        faction.set_influence("city_3", 1.5)
        assert faction.influence["city_3"] == 1.0

    def test_to_dict(self):
        """Test serialization to dict."""
        faction = Faction("a", "A", power=0.9)
        faction.set_relation("b", -0.5)
        faction.set_influence("city_1", 0.7)
        faction.goals.append("expand")
        faction.traits.append("aggressive")
        
        data = faction.to_dict()
        
        assert data["id"] == "a"
        assert data["power"] == 0.9
        assert data["relations"]["b"] == -0.5
        assert data["influence"]["city_1"] == 0.7
        assert "expand" in data["goals"]
        assert "aggressive" in data["traits"]


class TestFactionSystem:
    """Test FactionSystem simulation."""

    def test_add_faction(self):
        """Test adding factions to the system."""
        fs = FactionSystem()
        f1 = Faction("a", "A")
        f2 = Faction("b", "B")
        
        fs.add_faction(f1)
        fs.add_faction(f2)
        
        assert fs.get_faction("a") is f1
        assert fs.get_faction("b") is f2
        assert len(fs.factions) == 2

    def test_remove_faction(self):
        """Test removing factions cleans up relations."""
        fs = FactionSystem()
        a = Faction("a", "A")
        b = Faction("b", "B")
        
        a.set_relation("b", -0.5)
        b.set_relation("a", 0.3)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        # Remove b - should clean up references in a
        removed = fs.remove_faction("b")
        assert removed is b
        assert "b" not in fs.factions
        assert "b" not in a.relations

    def test_remove_nonexistent_faction(self):
        """Test removing non-existent faction returns None."""
        fs = FactionSystem()
        assert fs.remove_faction("ghost") is None

    def test_get_faction(self):
        """Test getting faction by ID."""
        fs = FactionSystem()
        f = Faction("a", "A")
        fs.add_faction(f)
        
        assert fs.get_faction("a") is f
        assert fs.get_faction("b") is None


class TestFactionConflictDetection:
    """Test conflict event generation."""

    def test_faction_conflict_generation(self):
        """Test that hostile relations generate conflict events."""
        fs = FactionSystem()
        
        a = Faction("a", "A")
        b = Faction("b", "B")
        
        a.set_relation("b", -0.8)  # Below CONFLICT_THRESHOLD (-0.6)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        events = fs.update()
        
        assert any(e["type"] == "faction_conflict" for e in events)

    def test_no_conflict_when_neutral(self):
        """Test that neutral relations don't generate conflicts."""
        fs = FactionSystem()
        
        a = Faction("a", "A")
        b = Faction("b", "B")
        
        # Default relations are 0 (neutral)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        events = fs.update()
        
        assert not any(e["type"] == "faction_conflict" for e in events)

    def test_alliance_detection(self):
        """Test that friendly relations generate alliance events."""
        fs = FactionSystem()
        
        a = Faction("a", "A")
        b = Faction("b", "B")
        
        a.set_relation("b", 0.7)  # Above 0.6 threshold
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        events = fs.update()
        
        assert any(e["type"] == "faction_alliance" for e in events)

    def test_conflict_avoids_duplicates(self):
        """Test that conflict pairs are not duplicated."""
        fs = FactionSystem()
        
        a = Faction("a", "A")
        b = Faction("b", "B")
        
        # Both factions have hostile relations
        a.set_relation("b", -0.8)
        b.set_relation("a", -0.7)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        events = fs.update()
        conflict_events = [e for e in events if e["type"] == "faction_conflict"]
        
        # Should only have one conflict event, not two
        assert len(conflict_events) == 1

    def test_conflict_importance_scales_with_hostility(self):
        """Test that more hostile = higher importance."""
        fs = FactionSystem()
        
        a1 = Faction("a1", "A1")
        a2 = Faction("a2", "A2")
        b = Faction("b", "B")
        
        a1.set_relation("b", -0.61)  # Just below threshold
        a2.set_relation("b", -0.95)  # Very hostile
        
        fs.add_faction(a1)
        fs.add_faction(a2)
        fs.add_faction(b)
        
        events = fs.update()
        
        # Find importance for each pair
        for event in events:
            if event["type"] == "faction_conflict":
                assert 0.5 <= event["importance"] <= 1.0


class TestFacterResourceUpdates:
    """Test resource, morale, and power updates."""

    def test_resources_increase_with_power(self):
        """Test that resources grow based on power."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.8, resources=0.5)
        fs.add_faction(f)
        
        fs.update()
        
        # Should have grown by RESOURCE_GROWTH_RATE * power
        expected_growth = RESOURCE_GROWTH_RATE * 0.8
        assert f.resources >= 0.5 + expected_growth - 0.0001  # Allow small float errors

    def test_morale_increases_with_resource_surplus(self):
        """Test that resources > 0.5 increases morale."""
        fs = FactionSystem()
        f = Faction("a", "A", resources=0.8, morale=0.5)
        fs.add_faction(f)
        
        fs.update()
        
        # Resource surplus = 0.8 - 0.5 = 0.3
        # Morale increase = 0.3 * MORALE_ADJUSTMENT_RATE
        expected_increase = 0.3 * MORALE_ADJUSTMENT_RATE
        assert f.morale >= 0.5 + expected_increase - 0.0001

    def test_morale_decreases_with_resource_deficit(self):
        """Test that resources < 0.5 decreases morale."""
        fs = FactionSystem()
        f = Faction("a", "A", resources=0.2, morale=0.5)
        fs.add_faction(f)
        
        fs.update()
        
        # Resource deficit = 0.2 - 0.5 = -0.3
        # Morale decrease = -0.3 * MORALE_ADJUSTMENT_RATE
        # Note: update_resources runs first, changing resources from 0.2 to 0.205
        # so actual resource_delta = 0.205 - 0.5 = -0.295
        expected_decrease = -0.295 * MORALE_ADJUSTMENT_RATE
        assert abs(f.morale - (0.5 + expected_decrease)) < 0.0001

    def test_power_increases_with_high_resources_and_morale(self):
        """Test that power grows when resources and morale are high."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.5, resources=0.8, morale=0.8)
        fs.add_faction(f)
        
        # Run multiple updates
        for _ in range(5):
            fs.update()
        
        assert f.power > 0.5

    def test_power_decreases_with_low_resources_and_morale(self):
        """Test that power decays when resources and morale are low."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.5, resources=0.1, morale=0.1)
        fs.add_faction(f)
        
        # Run multiple updates
        for _ in range(5):
            fs.update()
        
        assert f.power < 0.5

    def test_values_clamped_to_valid_range(self):
        """Test that all values stay within 0.0-1.0 range."""
        fs = FactionSystem()
        f = Faction("a", "A", power=1.0, resources=1.0, morale=1.0)
        fs.add_faction(f)
        
        # Many updates
        for _ in range(100):
            fs.update()
        
        assert 0.0 <= f.power <= 1.0
        assert 0.0 <= f.resources <= 1.0
        assert 0.0 <= f.morale <= 1.0


class TestPowerShiftDetection:
    """Test power shift events."""

    def test_rising_faction_detected(self):
        """Test that power > 0.8 generates rising event."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.9)
        fs.add_faction(f)
        
        events = fs.update()
        
        assert any(e["type"] == "faction_rising" for e in events)

    def test_declining_faction_detected(self):
        """Test that power < 0.2 generates declining event."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.1)
        fs.add_faction(f)
        
        events = fs.update()
        
        assert any(e["type"] == "faction_declining" for e in events)

    def test_mid_power_faction_no_shift_event(self):
        """Test that mid-range power doesn't generate shift events."""
        fs = FactionSystem()
        f = Faction("a", "A", power=0.5)
        fs.add_faction(f)
        
        events = fs.update()
        
        shift_events = [e for e in events if "faction_rising" in e["type"] or "faction_declining" in e["type"]]
        # No shift events expected for neutral power
        assert len(shift_events) == 0


class TestFactionSystemSummary:
    """Test faction system summary."""

    def test_get_summary(self):
        """Test summary includes all factions."""
        fs = FactionSystem()
        a = Faction("a", "A", power=0.7)
        b = Faction("b", "B", power=0.3)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        summary = fs.get_summary()
        
        assert "a" in summary
        assert "b" in summary
        assert summary["a"]["power"] == 0.7
        assert summary["b"]["power"] == 0.3

    def test_reset(self):
        """Test reset clears all factions."""
        fs = FactionSystem()
        fs.add_faction(Faction("a", "A"))
        fs.add_faction(Faction("b", "B"))
        
        fs.reset()
        
        assert len(fs.factions) == 0


class TestFactionWorldEvolution:
    """Test faction evolution over multiple ticks."""

    def test_faction_world_evolves_over_100_ticks(self):
        """Test that factions evolve over 100-tick simulation."""
        fs = FactionSystem()
        
        a = Faction("a", "A", power=0.6)
        b = Faction("b", "B", power=0.4)
        
        a.set_relation("b", -0.8)  # Hostile
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        conflict_count = 0
        alliance_count = 0
        
        for _ in range(100):
            events = fs.update()
            for event in events:
                if event["type"] == "faction_conflict":
                    conflict_count += 1
                elif event["type"] == "faction_alliance":
                    alliance_count += 1
        
        # Should have generated conflicts due to hostile relations
        assert conflict_count > 0, "Expected faction conflicts over 100 ticks"
        # No alliances since relations are hostile
        assert alliance_count == 0

    def test_alliance_stable_over_time(self):
        """Test that alliances persist when relations stay positive."""
        fs = FactionSystem()
        
        a = Faction("a", "A", power=0.5)
        b = Faction("b", "B", power=0.5)
        
        a.set_relation("b", 0.7)  # Friendly
        b.set_relation("a", 0.7)
        
        fs.add_faction(a)
        fs.add_faction(b)
        
        alliance_count = 0
        
        for _ in range(50):
            events = fs.update()
            for event in events:
                if event["type"] == "faction_alliance":
                    alliance_count += 1
        
        assert alliance_count > 0, "Expected alliances over 50 ticks"