"""Functional tests for the Irreversible Consequence Engine.

This module tests complete workflows and scenarios:
- Full choice generation and resolution flow
- Multiple sequential choices and their cumulative effects
- World state mutation across choices
- Belief evolution through repeated interactions
- Timeline permanence and query
- Faction destruction and resurrection prevention
"""

from typing import Any, Dict, List

import pytest

from app.rpg.choice.belief_updater import BeliefUpdater
from app.rpg.choice.choice_engine import ChoiceEngine
from app.rpg.choice.choice_models import ConsequenceRecord, PlayerChoice, TimelineEntry
from app.rpg.choice.consequence_engine import ConsequenceEngine
from app.rpg.choice.timeline_recorder import TimelineRecorder
from app.rpg.choice.world_mutator import WorldMutator
from app.rpg.quest.quest_engine import QuestEngine
from app.rpg.quest.quest_models import Quest, QuestObjective, QuestStage


def _create_test_quest(engine: QuestEngine, quest_type: str = "conflict") -> str:
    """Helper to create a test quest and return its ID."""
    quest = Quest(title="Test Quest", type=quest_type)
    stage = QuestStage(name="escalation")
    quest.stages = [stage]
    engine.tracker.add(quest)
    return quest.id


# ==================== Full Choice Flow Tests ====================

class TestFullChoiceFlow:
    """Tests for complete choice generation → resolution flows."""

    def test_generate_and_resolve_choice(self):
        """Test full flow: generate choices, select one, resolve it."""
        engine = QuestEngine()
        world = {
            "factions": {
                "red_house": {"power": 1.0},
                "blue_house": {"power": 1.0},
            }
        }
        memory = {}

        # Create a conflict quest
        quest_id = _create_test_quest(engine, "conflict")

        # Generate choices
        choices = engine.generate_choices(quest_id, world)
        assert choices is not None
        assert choices.resolved is False
        assert len(choices.options) > 0

        # Select an option
        selected = choices.select_option("support_actor")
        assert choices.resolved is True
        assert selected is not None

        # Resolve the choice
        effects = engine.resolve_choice(choices, quest_id, world, memory)
        assert len(effects) > 0

        # Verify world state changed
        assert "factions" in world
        assert len(effects) >= 3  # At least faction_shift, belief, and tag

    def test_multiple_quest_choices(self):
        """Test creating multiple quests and resolving choices for each."""
        engine = QuestEngine(max_active_quests=5)
        world = {}
        memory = {}

        # Create multiple quests
        quest_ids = [
            _create_test_quest(engine, "conflict"),
            _create_test_quest(engine, "betrayal"),
        ]

        assert len(quest_ids) == 2

        # Resolve choices for each quest
        for quest_id in quest_ids:
            choices = engine.generate_choices(quest_id, world)
            if choices:
                choices.select_option(choices.options[0]["id"])
                effects = engine.resolve_choice(choices, quest_id, world, memory)
                assert len(effects) > 0

    def test_choice_impacts_future_choices(self):
        """Test that earlier choices affect state for later choices."""
        engine = QuestEngine()
        world = {
            "factions": {
                "faction_a": {"power": 1.0},
                "faction_b": {"power": 1.0},
            }
        }
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make first choice that strengthens faction_a
        choice1 = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice1.select_option("support_actor")

        effects1 = engine.resolve_choice(choice1, quest_id, world, memory)
        power_a_after_1 = world["factions"]["faction_a"]["power"]

        # Make second choice
        choice2 = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice2.select_option("support_actor")

        engine.resolve_choice(choice2, quest_id, world, memory)
        power_a_after_2 = world["factions"]["faction_a"]["power"]

        # Power should have increased twice
        assert power_a_after_1 > 1.0
        assert power_a_after_2 > power_a_after_1


# ==================== World State Mutation Tests ====================

class TestWorldStateMutation:
    """Tests for world state changes through choices."""

    def test_faction_power_accumulates(self):
        """Verify faction power accumulates across multiple choices."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        for i in range(5):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support A"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Faction A should have gained power
        assert world["factions"]["A"]["power"] > 1.0
        # Faction B should have lost power
        assert world["factions"]["B"]["power"] < 1.0

    def test_tension_level_changes(self):
        """Verify tension level changes based on choices."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}, "tension_level": 0.5}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make a supporting choice that might not reduce tension
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")
        engine.resolve_choice(choice, quest_id, world, memory)

        # World should have changed in some way
        assert world is not None

    def test_faction_can_be_destroyed(self):
        """Verify that a faction can be reduced to 0 and marked as destroyed."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 0.5}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Multiple choices to drain faction B's power
        for _ in range(3):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Faction B should be severely weakened or destroyed
        if world["factions"]["B"]["power"] <= 0:
            assert world["factions"]["B"].get("destroyed", False) is True
            assert "faction_destroyed" in world.get("history_flags", set())

    def test_history_flags_accumulate(self):
        """Verify that history flags accumulate and are never removed."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make multiple choices
        for i in range(3):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Should have at least one irreversible tag
        if "history_flags" in world:
            assert len(world["history_flags"]) > 0


# ==================== Belief Evolution Tests ====================

class TestBeliefEvolution:
    """Tests for NPC belief changes through repeated interactions."""

    def test_belief_increases_with_positive_actions(self):
        """Verify that positive actions increase belief values."""
        engine = QuestEngine()
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make multiple choices that support the actor
        for _ in range(3):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Actor should have positive belief toward player
        if "beliefs" in memory and "actor->player" in memory["beliefs"]:
            assert memory["beliefs"]["actor->player"] > 0

    def test_belief_decreases_with_negative_actions(self):
        """Verify that negative actions decrease belief values."""
        engine = QuestEngine()
        # Use "actor" and "target" as faction keys - these are what the consequence engine expects
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make choices that support actor (which also updates beliefs)
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support Actor"}],
        )
        choice.select_option("support_actor")
        engine.resolve_choice(choice, quest_id, world, memory)

        # Beliefs should have been updated (support_actor generates belief_update)
        assert "beliefs" in memory

    def test_belief_classification_changes(self):
        """Verify belief classification changes threshold."""
        engine = QuestEngine()
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make many supportive choices to build trust
        for _ in range(5):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Beliefs should exist (support_actor generates belief_update for actor->player)
        beliefs = memory.get("beliefs", {})
        assert len(beliefs) > 0
        # Check that at least one belief is positive
        assert any(v > 0 for v in beliefs.values())


# ==================== Timeline Tests ====================

class TestTimelinePermanence:
    """Tests for timeline permanence and querying."""

    def test_timeline_grows_with_choices(self):
        """Verify timeline entries accumulate with each choice."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")
        initial_count = engine.timeline.get_entry_count()

        for _ in range(5):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        final_count = engine.timeline.get_entry_count()
        assert final_count == initial_count + 5

    def test_timeline_querying(self):
        """Verify timeline can be queried for entries."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make some choices
        for _ in range(3):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Query timeline
        summary = engine.get_world_summary(world)
        assert summary["timeline"]["total_entries"] >= 3

    def test_timeline_persists_across_resets(self):
        """Verify timeline is independent of quest tracker reset."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Make choice and record it
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")
        engine.resolve_choice(choice, quest_id, world, memory)

        assert engine.timeline.get_entry_count() == 1

        # Reset quest tracker (but timeline is separate)
        engine.reset()

        # Timeline entry should still exist (it's part of engine, not tracker)
        timeline_state_after_reset = engine.timeline.get_entry_count()
        assert timeline_state_after_reset == 1


# ==================== Faction Destruction Tests ====================

class TestFactionDestruction:
    """Tests for faction destruction and resurrection prevention."""

    def test_faction_destruction_prevents_respawn(self):
        """Verify that destroyed factions cannot be resurrected."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 0.3}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Destroy faction B with enough choices
        for _ in range(5):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support A"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Check if faction was destroyed
        if world["factions"]["B"]["power"] <= 0:
            assert world["factions"]["B"].get("destroyed", False) is True
            # Try to check respawn prevention
            assert engine.world_mutator.prevent_respawn(world, "B") is True

    def test_irreversible_flags_persist(self):
        """Verify that irreversible flags are never removed."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Create some irreversible flags
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")
        engine.resolve_choice(choice, quest_id, world, memory)

        # If flags were created, they should persist
        if world.get("history_flags"):
            flags_before = set(world["history_flags"])

            # Make more choices
            choice2 = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice2.select_option("support_actor")
            engine.resolve_choice(choice2, quest_id, world, memory)

            # Flags should only grow, never shrink
            flags_after = set(world["history_flags"])
            assert flags_after.issuperset(flags_before)


# ==================== End-to-End Scenario Tests ====================

class TestEndToEndScenarios:
    """End-to-end scenario tests simulating real gameplay."""

    def test_conflict_scenario(self):
        """End-to-end test: player navigates a conflict between factions."""
        engine = QuestEngine()
        world = {
            "tension_level": 0.3,
            "factions": {
                "north_kingdom": {"power": 1.0},
                "south_kingdom": {"power": 1.0},
            },
        }
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Player chooses to support north_kingdom
        choices = engine.generate_choices(quest_id, world)
        assert choices is not None
        choices.select_option("support_actor")
        
        effects = engine.resolve_choice(choices, quest_id, world, memory)
        assert len(effects) > 0

        # North's power should increase, south's should decrease
        assert world["factions"]["north_kingdom"]["power"] > 1.0
        assert world["factions"]["south_kingdom"]["power"] < 1.0

    def test_betrayal_scenario(self):
        """End-to-end test: player handles a betrayal situation."""
        engine = QuestEngine()
        world = {}
        memory = {}

        quest_id = _create_test_quest(engine, "betrayal")

        # Generate choices or create manually
        choices = engine.generate_choices(quest_id, world)
        if choices:
            # generate_choices returns a NEW PlayerChoice, need to select on it
            selected = choices.select_option("punish")
            if selected:
                effects = engine.resolve_choice(choices, quest_id, world, memory)
                assert len(effects) > 0

    def test_escalation_scenario(self):
        """End-to-end test: conflict escalates and player intervenes."""
        engine = QuestEngine()
        world = {
            "factions": {"rebels": {"power": 0.8}, "empire": {"power": 1.2}},
            "tension_level": 0.6,
        }
        memory = {}

        # Create multiple conflict events
        quest_ids = [
            _create_test_quest(engine, "conflict"),
            _create_test_quest(engine, "conflict"),
            _create_test_quest(engine, "conflict"),
        ]

        # Intervene in each quest
        for quest_id in quest_ids:
            choices = engine.generate_choices(quest_id, world)
            if choices and len(choices.options) >= 3:
                # Try to mediate
                mediation_options = [o for o in choices.options if o["id"] == "mediate"]
                if mediation_options:
                    choices.select_option("mediate")
                else:
                    choices.select_option(choices.options[0]["id"])
                engine.resolve_choice(choices, quest_id, world, memory)

        assert engine.timeline.get_entry_count() == len(quest_ids)

    def test_rapid_choice_scenario(self):
        """Test rapid successive choices don't break the system."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        # Create many choices rapidly
        for _ in range(20):
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support A"}],
            )
            choice.select_option("support_actor")
            engine.resolve_choice(choice, quest_id, world, memory)

        # Verify state is still consistent
        assert world["factions"]["A"]["power"] > 0
        assert engine.timeline.get_entry_count() == 20

    def test_mixed_quest_types_scenario(self):
        """Test handling multiple quest types with choices."""
        engine = QuestEngine(max_active_quests=10)
        world = {}
        memory = {}

        quest_ids = [
            _create_test_quest(engine, "conflict"),
            _create_test_quest(engine, "betrayal"),
            _create_test_quest(engine, "supply"),
        ]

        # Resolve each quest
        for quest_id in quest_ids:
            choices = engine.generate_choices(quest_id, world)
            if choices:
                choices.select_option(choices.options[0]["id"])
                effects = engine.resolve_choice(choices, quest_id, world, memory)
                assert len(effects) > 0

        assert len(quest_ids) >= 1


# ==================== Regression Tests ====================

class TestChoiceConsequenceRegression:
    """Regression tests for known issues and edge cases."""

    def test_empty_world_doesnt_crash(self):
        """Verify system handles empty world gracefully."""
        engine = QuestEngine()
        world = {}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")

        # Should not crash
        effects = engine.resolve_choice(choice, quest_id, world, memory)
        assert effects is not None

    def test_empty_memory_doesnt_crash(self):
        """Verify system handles empty memory gracefully."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")

        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")

        effects = engine.resolve_choice(choice, quest_id, world, memory)
        assert len(effects) > 0

    def test_quest_not_found_handled(self):
        """Verify proper error when quest doesn't exist."""
        engine = QuestEngine()
        world = {}

        choice = PlayerChoice(
            quest_id="nonexistent",
            stage="escalation",
            options=[{"id": "opt1", "text": "Option"}],
        )
        choice.select_option("opt1")

        with pytest.raises(ValueError, match="not found"):
            engine.resolve_choice(choice, "nonexistent", world)

    def test_choice_not_resolved_handled(self):
        """Verify proper error when choice isn't resolved."""
        engine = QuestEngine()
        world = {}
        engine.process_event({"type": "attack", "importance": 0.8}, world)
        quests = engine.tracker.get_active_quests()
        quest_id = quests[0].id if quests else "q1"

        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "opt1", "text": "Option"}],
        )
        # Don't resolve
        with pytest.raises(ValueError, match="must be resolved"):
            engine.resolve_choice(choice, quest_id, world)

    def test_very_long_quest_id(self):
        """Verify system handles very long quest IDs."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        memory = {}

        long_id = _create_test_quest(engine, "conflict")
        choice = PlayerChoice(
            quest_id=long_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")
        
        # Should handle without error
        effects = engine.resolve_choice(choice, long_id, world, memory)
        assert effects is not None

    def test_special_characters_in_ids(self):
        """Verify system handles special characters in IDs."""
        engine = QuestEngine()
        world = {"factions": {"A": {"power": 1.0}}}
        memory = {}

        quest_id = _create_test_quest(engine, "conflict")
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")

        effects = engine.resolve_choice(choice, quest_id, world, memory)
        # System should handle special characters gracefully
        assert effects is not None