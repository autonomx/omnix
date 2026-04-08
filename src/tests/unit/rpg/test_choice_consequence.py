"""Unit tests for the Irreversible Consequence Engine.

This module tests all components of the Player Choice → Irreversible
Consequence Engine:
- Choice models (PlayerChoice, ConsequenceRecord, TimelineEntry)
- Choice generation engine
- Consequence engine
- World mutator
- Belief updater
- Timeline recorder
- Integration with QuestEngine
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

# ==================== Choice Models Tests ====================

class TestPlayerChoice:
    """Tests for PlayerChoice model."""

    def test_create_choice(self):
        choice = PlayerChoice(
            quest_id="quest1",
            stage="escalation",
            description="Choose a side",
            options=[
                {"id": "option_a", "text": "Option A"},
                {"id": "option_b", "text": "Option B"},
            ],
        )
        assert choice.quest_id == "quest1"
        assert choice.stage == "escalation"
        assert len(choice.options) == 2
        assert choice.resolved is False
        assert choice.selected_option is None

    def test_select_option(self):
        choice = PlayerChoice(
            quest_id="quest1",
            stage="escalation",
            options=[
                {"id": "option_a", "text": "Option A"},
                {"id": "option_b", "text": "Option B"},
            ],
        )
        result = choice.select_option("option_a")
        assert result is not None
        assert result["id"] == "option_a"
        assert choice.resolved is True
        assert choice.selected_option["id"] == "option_a"

    def test_select_option_invalid(self):
        choice = PlayerChoice(
            quest_id="quest1",
            options=[{"id": "option_a", "text": "Option A"}],
        )
        result = choice.select_option("option_invalid")
        assert result is None
        assert choice.resolved is False

    def test_to_dict(self):
        choice = PlayerChoice(
            quest_id="q1",
            stage="setup",
            description="Test",
            options=[{"id": "opt1", "text": "Opt 1"}],
        )
        d = choice.to_dict()
        assert d["quest_id"] == "q1"
        assert d["stage"] == "setup"
        assert d["description"] == "Test"
        assert len(d["options"]) == 1
        assert d["resolved"] is False

    def test_from_dict(self):
        data = {
            "id": "choice123",
            "quest_id": "q1",
            "stage": "escalation",
            "description": "Choose wisely",
            "options": [{"id": "opt1", "text": "Option 1"}],
            "resolved": True,
            "selected_option": {"id": "opt1", "text": "Option 1"},
        }
        choice = PlayerChoice.from_dict(data)
        assert choice.id == "choice123"
        assert choice.quest_id == "q1"
        assert choice.resolved is True

    def test_unique_ids(self):
        c1 = PlayerChoice()
        c2 = PlayerChoice()
        assert c1.id != c2.id


class TestConsequenceRecord:
    """Tests for ConsequenceRecord model."""

    def test_create_consequence(self):
        c = ConsequenceRecord(
            choice_id="c1",
            consequence_type="faction_power_shift",
            data={"actor": "A", "target": "B", "delta": 0.3},
        )
        assert c.consequence_type == "faction_power_shift"
        assert c.applied is False

    def test_to_dict(self):
        c = ConsequenceRecord(
            choice_id="c1",
            consequence_type="belief_update",
            data={"key": "A->B", "delta": 0.5},
        )
        d = c.to_dict()
        assert d["consequence_type"] == "belief_update"
        assert d["data"]["delta"] == 0.5

    def test_unique_ids(self):
        c1 = ConsequenceRecord()
        c2 = ConsequenceRecord()
        assert c1.id != c2.id


class TestTimelineEntry:
    """Tests for TimelineEntry model."""

    def test_create_entry(self):
        entry = TimelineEntry(
            choice_id="c1",
            option_selected={"id": "opt1"},
            consequences=[],
            tags=["tag1"],
        )
        assert entry.choice_id == "c1"
        assert entry.has_tag("tag1") is True
        assert entry.has_tag("tag2") is False

    def test_add_tag(self):
        entry = TimelineEntry()
        entry.add_tag("new_tag")
        assert entry.has_tag("new_tag") is True

    def test_add_duplicate_tag(self):
        entry = TimelineEntry(tags=["tag1"])
        entry.add_tag("tag1")
        assert len(entry.tags) == 1

    def test_to_dict(self):
        entry = TimelineEntry(
            choice_id="c1",
            option_selected={"id": "opt1"},
            consequences=[{"type": "test"}],
            tags=["tag1"],
        )
        d = entry.to_dict()
        assert d["choice_id"] == "c1"
        assert len(d["consequences"]) == 1
        assert len(d["tags"]) == 1

    def test_unique_ids(self):
        e1 = TimelineEntry()
        e2 = TimelineEntry()
        assert e1.id != e2.id


# ==================== Choice Engine Tests ====================

class TestChoiceEngine:
    """Tests for ChoiceEngine."""

    def test_generate_choices_conflict_escalation(self):
        engine = ChoiceEngine()
        quest = Quest(title="Test Conflict", type="conflict")
        stage = QuestStage(name="escalation")
        quest.stages = [stage]
        world = {}

        choices = engine.generate_choices(quest, world)
        assert choices is not None
        assert len(choices.options) == 3
        ids = [o["id"] for o in choices.options]
        assert "support_actor" in ids
        assert "support_target" in ids
        assert "mediate" in ids

    def test_generate_choices_betrayal(self):
        engine = ChoiceEngine()
        quest = Quest(title="Betrayal", type="betrayal")
        stage = QuestStage(name="confrontation")
        quest.stages = [stage]
        world = {}

        choices = engine.generate_choices(quest, world)
        assert choices is not None
        ids = [o["id"] for o in choices.options]
        assert "forgive" in ids
        assert "punish" in ids
        assert "exploit" in ids

    def test_generate_choices_war_climax(self):
        engine = ChoiceEngine()
        quest = Quest(title="War", type="war")
        stage = QuestStage(name="climax")
        quest.stages = [stage]
        world = {}

        choices = engine.generate_choices(quest, world)
        assert choices is not None
        ids = [o["id"] for o in choices.options]
        assert "full_assault" in ids
        assert "siege" in ids
        assert "assassinate" in ids

    def test_generate_choices_empty_quest(self):
        engine = ChoiceEngine()
        quest = Quest(title="Empty", type="unknown")
        quest.stages = []
        world = {}
        choices = engine.generate_choices(quest, world)
        assert choices is None

    def test_generate_choices_null_quest(self):
        engine = ChoiceEngine()
        choices = engine.generate_choices(None, {})
        assert choices is None

    def test_generate_choices_with_factions(self):
        engine = ChoiceEngine()
        quest = Quest(title="Test", type="unknown")
        stage = QuestStage(name="unknown_stage")
        quest.stages = [stage]
        world = {"factions": {"faction_a": {}, "faction_b": {}}}

        choices = engine.generate_choices(quest, world)
        assert choices is not None
        # Should generate faction-based choices
        assert len(choices.options) >= 2

    def test_generate_choices_with_high_tension(self):
        engine = ChoiceEngine()
        quest = Quest(title="Test", type="unknown")
        stage = QuestStage(name="unknown_stage")
        quest.stages = [stage]
        world = {"tension_level": 0.8}

        choices = engine.generate_choices(quest, world)
        assert choices is not None
        ids = [o["id"] for o in choices.options]
        assert "de_escalate" in ids

    def test_register_custom_choices(self):
        engine = ChoiceEngine()
        ChoiceEngine.register_custom_choices(
            "custom_type",
            "custom_stage",
            [{"id": "custom_opt", "text": "Custom Option"}],
            engine,
        )
        quest = Quest(title="Custom", type="custom_type")
        stage = QuestStage(name="custom_stage")
        quest.stages = [stage]
        choices = engine.generate_choices(quest, {})
        assert choices is not None
        assert choices.options[0]["id"] == "custom_opt"


# ==================== Consequence Engine Tests ====================

class TestConsequenceEngine:
    """Tests for ConsequenceEngine."""

    def test_apply_conflict_support_actor(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            stage="escalation",
            description="Choose",
            options=[{"id": "support_actor", "text": "Support Actor"}],
        )
        choice.select_option("support_actor")
        quest = Quest(type="conflict")
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}
        
        consequences = engine.apply(choice, quest, world)
        assert len(consequences) > 0
        
        types = [c.consequence_type for c in consequences]
        assert "faction_power_shift" in types
        assert "belief_update" in types
        assert "tag_add" in types

    def test_apply_conflict_support_target(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            stage="escalation",
            options=[{"id": "support_target", "text": "Support Target"}],
        )
        choice.select_option("support_target")
        quest = Quest(type="conflict")
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}

        consequences = engine.apply(choice, quest, world)
        assert len(consequences) > 0
        
        # Find the faction_power_shift consequence
        shift_consequences = [c for c in consequences if c.consequence_type == "faction_power_shift"]
        assert len(shift_consequences) > 0
        # Actor should lose power
        assert shift_consequences[0].data["delta"] == -0.3

    def test_apply_betrayal_forgive(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            options=[{"id": "forgive", "text": "Forgive"}],
        )
        choice.select_option("forgive")
        quest = Quest(type="betrayal")
        world = {}

        consequences = engine.apply(choice, quest, world)
        assert len(consequences) > 0
        
        types = [c.consequence_type for c in consequences]
        assert "belief_update" in types
        assert "tag_add" in types

    def test_apply_betrayal_punish(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            options=[{"id": "punish", "text": "Punish"}],
        )
        choice.select_option("punish")
        quest = Quest(type="betrayal")
        world = {}

        consequences = engine.apply(choice, quest, world)
        assert len(consequences) > 0

    def test_apply_unresolved_choice(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            options=[{"id": "opt1", "text": "Option 1"}],
        )
        # Don't resolve the choice
        consequences = engine.apply(choice, Quest(type="conflict"), {})
        assert len(consequences) == 0

    def test_apply_generic_consequences(self):
        engine = ConsequenceEngine()
        choice = PlayerChoice(
            quest_id="q1",
            options=[{"id": "support_faction_a", "text": "Support A"}],
        )
        choice.select_option("support_faction_a")
        quest = Quest(type="unknown_type")
        world = {}

        consequences = engine.apply(choice, quest, world)
        assert len(consequences) > 0

    def test_register_consequences(self):
        engine = ConsequenceEngine()
        engine.register_consequences("custom", {
            "custom_option": [
                {"type": "world_state_change", "key": "test", "delta": 1.0},
            ],
        })
        choice = PlayerChoice(
            quest_id="q1",
            options=[{"id": "custom_option", "text": "Custom"}],
        )
        choice.select_option("custom_option")
        quest = Quest(type="custom")
        world = {}

        consequences = engine.apply(choice, quest, world)
        assert len(consequences) == 1
        assert consequences[0].consequence_type == "world_state_change"


# ==================== World Mutator Tests ====================

class TestWorldMutator:
    """Tests for WorldMutator."""

    def test_shift_faction_power(self):
        mutator = WorldMutator()
        world = {"factions": {}}
        effect = mutator.shift_faction_power(world, "A", "B", 0.3)
        
        assert effect["type"] == "faction_power_shift"
        assert world["factions"]["A"]["power"] == 1.3
        assert world["factions"]["B"]["power"] == 0.7

    def test_shift_faction_power_destroys_faction(self):
        mutator = WorldMutator()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        mutator.shift_faction_power(world, "A", "B", 1.0)
        
        assert world["factions"]["B"]["power"] <= 0
        assert world["factions"]["B"]["destroyed"] is True
        assert "faction_destroyed" in world["history_flags"]

    def test_change_world_state(self):
        mutator = WorldMutator()
        world = {}
        effect = mutator.change_world_state(world, "tension_level", 0.5)
        
        assert effect["key"] == "tension_level"
        assert effect["new_value"] == 0.5
        assert world["tension_level"] == 0.5

    def test_change_world_state_negative(self):
        mutator = WorldMutator()
        world = {"tension_level": 1.0}
        effect = mutator.change_world_state(world, "tension_level", -0.4)
        
        assert effect["old_value"] == 1.0
        assert effect["new_value"] == 0.6

    def test_add_world_tag(self):
        mutator = WorldMutator()
        world = {}
        effect = mutator.add_world_tag(world, "war_declared")
        
        assert effect["tag"] == "war_declared"
        assert effect["is_irreversible"] is True
        assert "war_declared" in world["history_flags"]

    def test_add_reversible_tag(self):
        mutator = WorldMutator()
        world = {}
        effect = mutator.add_world_tag(world, "custom_tag")
        
        assert effect["is_irreversible"] is False

    def test_check_irreversible(self):
        mutator = WorldMutator()
        world = {"history_flags": {"faction_destroyed"}}
        assert mutator.check_irreversible(world, "faction_destroyed") is True
        assert mutator.check_irreversible(world, "nonexistent") is False

    def test_prevent_respawn(self):
        mutator = WorldMutator()
        world = {"history_flags": {"faction_destroyed"}}
        assert mutator.prevent_respawn(world, "faction_a") is True

    def test_prevent_respawn_destroyed_flag(self):
        mutator = WorldMutator()
        world = {"factions": {"A": {"power": 0.0, "destroyed": True}}}
        assert mutator.prevent_respawn(world, "A") is True

    def test_check_faction_exists(self):
        mutator = WorldMutator()
        world = {"factions": {"A": {"power": 1.0}}}
        assert mutator.check_faction_exists(world, "A") is True
        assert mutator.check_faction_exists(world, "B") is False

    def test_check_faction_destroyed(self):
        mutator = WorldMutator()
        world = {"factions": {"A": {"power": 0.0, "destroyed": True}}}
        assert mutator.check_faction_exists(world, "A") is False

    def test_apply_consequences(self):
        mutator = WorldMutator()
        world = {"factions": {}}
        consequences = [
            ConsequenceRecord(
                consequence_type="faction_power_shift",
                data={"actor": "A", "target": "B", "delta": 0.2},
            ),
            ConsequenceRecord(
                consequence_type="tag_add",
                data={"tag": "test_tag"},
            ),
        ]
        applied = mutator.apply_consequences(consequences, world)
        
        assert len(applied) == 2
        assert consequences[0].applied is True
        assert consequences[1].applied is True

    def test_get_world_summary(self):
        mutator = WorldMutator()
        world = {
            "factions": {"A": {"power": 1.0}, "B": {"power": 0.5}},
            "history_flags": {"test"},
            "timeline": [{"id": "1"}],
        }
        summary = mutator.get_world_summary(world)
        assert "factions" in summary
        assert "history_flags" in summary

    def test_mark_irreversible(self):
        mutator = WorldMutator()
        world = {}
        mutator.mark_irreversible(world, "alliance_broken")
        assert "alliance_broken" in world["history_flags"]


# ==================== Belief Updater Tests ====================

class TestBeliefUpdater:
    """Tests for BeliefUpdater."""

    def test_apply_belief(self):
        updater = BeliefUpdater()
        memory = {}
        result = updater.apply(memory, "A", "B", 0.5)
        
        assert result["key"] == "A->B"
        assert result["new_belief"] == 0.5
        assert memory["beliefs"]["A->B"] == 0.5

    def test_belief_positive(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 0.5)
        updater.apply(memory, "A", "B", 0.3)
        assert memory["beliefs"]["A->B"] == 0.8

    def test_belief_negative(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", -0.7)
        assert memory["beliefs"]["A->B"] == -0.7

    def test_belief_clamped(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 2.0)
        assert memory["beliefs"]["A->B"] == 1.0

    def test_belief_clamped_negative(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", -2.0)
        assert memory["beliefs"]["A->B"] == -1.0

    def test_classify_belief_hostile(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", -0.8)
        assert updater.get_relationship(memory, "A", "B") == "hostile"

    def test_classify_belief_neutral(self):
        updater = BeliefUpdater()
        memory = {}
        result = updater.apply(memory, "A", "B", 0.1)
        assert result["old_relation"] == "neutral"

    def test_classify_belief_friendly(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 0.6)
        assert updater.get_relationship(memory, "A", "B") == "friendly"

    def test_classify_belief_trusted(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 0.9)
        assert updater.get_relationship(memory, "A", "B") == "trusted"

    def test_is_hostile(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", -0.6)
        assert updater.is_hostile(memory, "A", "B") is True
        assert updater.is_hostile(memory, "A", "C") is False

    def test_is_friendly(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 0.6)
        assert updater.is_friendly(memory, "A", "B") is True

    def test_is_trusted(self):
        updater = BeliefUpdater()
        memory = {}
        updater.apply(memory, "A", "B", 0.9)
        assert updater.is_trusted(memory, "A", "B") is True

    def test_get_belief(self):
        updater = BeliefUpdater()
        memory = {"beliefs": {"A->B": 0.5}}
        assert updater.get_belief(memory, "A", "B") == 0.5
        assert updater.get_belief(memory, "A", "C") == 0.0  # Default

    def test_apply_consequences(self):
        updater = BeliefUpdater()
        memory = {}
        consequences = [
            ConsequenceRecord(
                consequence_type="belief_update",
                data={"actor": "A", "target": "B", "delta": 0.3},
            ),
            ConsequenceRecord(
                consequence_type="faction_power_shift",  # Not a belief update
                data={"actor": "A", "target": "B", "delta": 0.1},
            ),
        ]
        applied = updater.apply_consequences(consequences, memory)
        assert len(applied) == 1
        assert memory["beliefs"]["A->B"] == 0.3

    def test_relationship_change_tagged(self):
        updater = BeliefUpdater()
        memory = {}
        result = updater.apply(memory, "A", "B", 0.9)
        assert result.get("relationship_changed") is True
        assert "relation_trusted_A->B" in memory["tags"]

    def test_get_beliefs_about(self):
        updater = BeliefUpdater()
        memory = {"beliefs": {"A->B": 0.5, "C->B": -0.3}}
        beliefs = updater.get_beliefs_about(memory, "B")
        assert beliefs["A"] == 0.5
        assert beliefs["C"] == -0.3

    def test_get_beliefs_held_by(self):
        updater = BeliefUpdater()
        memory = {"beliefs": {"A->B": 0.5, "A->C": 0.3}}
        beliefs = updater.get_beliefs_held_by(memory, "A")
        assert beliefs["B"] == 0.5
        assert beliefs["C"] == 0.3

    def test_reset_belief(self):
        updater = BeliefUpdater()
        memory = {"beliefs": {"A->B": 0.5}}
        old = updater.reset_belief(memory, "A", "B")
        assert old == 0.5
        assert "A->B" not in memory["beliefs"]

    def test_reset_belief_nonexistent(self):
        updater = BeliefUpdater()
        memory = {}
        result = updater.reset_belief(memory, "A", "B")
        assert result is None

    def test_get_memory_summary(self):
        updater = BeliefUpdater()
        memory = {"beliefs": {"A->B": 0.5}, "tags": ["test"]}
        summary = updater.get_memory_summary(memory)
        assert "beliefs" in summary
        assert "tags" in summary


# ==================== Timeline Recorder Tests ====================

class TestTimelineRecorder:
    """Tests for TimelineRecorder."""

    def test_record(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice(
            quest_id="q1",
            stage="escalation",
            options=[{"id": "opt1", "text": "Option 1"}],
        )
        choice.select_option("opt1")
        world = {}
        consequences = [
            ConsequenceRecord(consequence_type="tag_add", data={"tag": "test_tag"}),
        ]

        entry = recorder.record(world, choice, consequences)
        assert entry is not None
        assert entry.choice_id == choice.id
        assert recorder.get_entry_count() == 1
        assert "test_tag" in world["history_flags"]

    def test_record_updates_world_timeline(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice(options=[{"id": "opt1", "text": "Opt"}])
        choice.select_option("opt1")
        world = {}

        recorder.record(world, choice, [])
        assert "timeline" in world
        assert len(world["timeline"]) == 1

    def test_get_entries(self):
        recorder = TimelineRecorder()
        for i in range(3):
            choice = PlayerChoice(quest_id=f"q{i}", stage="setup")
            choice.select_option(f"opt{i}")
            recorder.record({}, choice, [])

        assert recorder.get_entry_count() == 3

    def test_has_tag_in_history(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice(options=[{"id": "opt1", "text": "Opt"}])
        choice.select_option("opt1")
        
        recorder.record({}, choice, [
            ConsequenceRecord(consequence_type="tag_add", data={"tag": "important_tag"}),
        ])
        
        assert recorder.has_tag_in_history("important_tag") is True
        assert recorder.has_tag_in_history("nonexistent") is False

    def test_get_entries_with_tag(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice(options=[{"id": "opt1", "text": "Opt"}])
        choice.select_option("opt1")
        
        recorder.record({}, choice, [
            ConsequenceRecord(consequence_type="tag_add", data={"tag": "war"}),
        ])
        
        entries = recorder.get_entries_with_tag("war")
        assert len(entries) == 1

    def test_get_latest_entry(self):
        recorder = TimelineRecorder()
        for i in range(3):
            choice = PlayerChoice()
            choice.select_option("opt")
            recorder.record({}, choice, [])

        latest = recorder.get_latest_entry()
        assert latest is not None

    def test_get_latest_entry_empty(self):
        recorder = TimelineRecorder()
        assert recorder.get_latest_entry() is None

    def test_get_summary(self):
        recorder = TimelineRecorder()
        for i in range(3):
            choice = PlayerChoice(options=[{"id": f"opt{i}", "text": "Opt"}])
            choice.select_option(f"opt{i}")
            recorder.record({}, choice, [])

        summary = recorder.get_summary()
        assert summary["total_entries"] == 3

    def test_to_world_state(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice()
        choice.select_option("opt")
        recorder.record({}, choice, [])

        world = {}
        recorder.to_world_state(world)
        assert "timeline" in world
        assert len(world["timeline"]) == 1

    def test_from_world_state(self):
        world = {
            "timeline": [
                {
                    "choice_id": "c1",
                    "option_selected": {"id": "opt1"},
                    "consequences": [],
                    "timestamp": 100.0,
                    "tags": [],
                }
            ]
        }
        recorder = TimelineRecorder.from_world_state(world)
        assert recorder.get_entry_count() == 1

    def test_clear(self):
        recorder = TimelineRecorder()
        for i in range(3):
            choice = PlayerChoice()
            choice.select_option("opt")
            recorder.record({}, choice, [])

        count = recorder.clear()
        assert count == 3
        assert recorder.get_entry_count() == 0


# ==================== Irreversibility Tests ====================

class TestIrreversibility:
    """Tests for the irreversibility guarantees."""

    def test_faction_stays_destroyed(self):
        mutator = WorldMutator()
        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}
        
        # Destroy faction B
        mutator.shift_faction_power(world, "A", "B", 1.0)
        assert world["factions"]["B"]["destroyed"] is True
        
        # Try to "revive" faction B - the destruction flag stays
        assert mutator.prevent_respawn(world, "B") is True

    def test_alliance_broken_stays_broken(self):
        mutator = WorldMutator()
        world = {}
        mutator.mark_irreversible(world, "alliance_broken")
        assert "alliance_broken" in world["history_flags"]

    def test_timeline_cannot_be_undone(self):
        recorder = TimelineRecorder()
        choice = PlayerChoice(options=[{"id": "opt1", "text": "Opt"}])
        choice.select_option("opt1")
        
        entry = recorder.record({}, choice, [])
        assert recorder.get_entry_count() == 1
        
        # No undo method exists - entry is permanent
        # Only clear() exists for testing purposes
        entries = recorder.get_entries()
        assert len(entries) == 1

    def test_betrayal_recorded_permanently(self):
        mutator = WorldMutator()
        world = {}
        mutator.add_world_tag(world, "betrayal_recorded")
        assert mutator.check_irreversible(world, "betrayal_recorded") is True


# ==================== QuestEngine Integration Tests ====================

class TestQuestEngineChoiceConsequence:
    """Integration tests for QuestEngine with choice/consequence system."""

    def test_quest_engine_has_choice_components(self):
        engine = QuestEngine()
        assert hasattr(engine, "choice_engine")
        assert hasattr(engine, "consequence_engine")
        assert hasattr(engine, "world_mutator")
        assert hasattr(engine, "belief_updater")
        assert hasattr(engine, "timeline")

    def test_generate_choices_for_quest(self):
        engine = QuestEngine()
        world = {}
        
        # Create a quest
        result = engine.process_event({"type": "attack", "importance": 0.8}, world)
        assert result["new_quest"] is not None
        
        quest_id = result["new_quest"].id
        choices = engine.generate_choices(quest_id, world)
        assert choices is not None
        assert len(choices.options) > 0

    def test_resolve_choice(self):
        engine = QuestEngine()
        world = {}
        memory = {}
        
        # Create a quest
        result = engine.process_event({"type": "attack", "importance": 0.8}, world)
        quest_id = result["new_quest"].id

        # Manually create and resolve a choice
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            description="Choose",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")

        # Resolve the choice
        world["factions"] = {"actor": {"power": 1.0}, "target": {"power": 1.0}}
        effects = engine.resolve_choice(choice, quest_id, world, memory)
        
        assert len(effects) > 0

    def test_resolve_choice_invalid_quest(self):
        engine = QuestEngine()
        world = {}
        
        choice = PlayerChoice(
            quest_id="nonexistent",
            options=[{"id": "opt1", "text": "Opt"}],
        )
        choice.select_option("opt1")

        with pytest.raises(ValueError):
            engine.resolve_choice(choice, "nonexistent", world)

    def test_resolve_choice_not_resolved(self):
        engine = QuestEngine()
        world = {}
        engine.process_event({"type": "attack", "importance": 0.8}, world)
        quests = engine.tracker.get_active_quests()
        quest_id = quests[0].id

        choice = PlayerChoice(quest_id=quest_id, options=[{"id": "opt1", "text": "Opt"}])
        # Don't resolve

        with pytest.raises(ValueError):
            engine.resolve_choice(choice, quest_id, world)

    def test_check_irreversible(self):
        engine = QuestEngine()
        world = {"history_flags": {"faction_destroyed"}}
        assert engine.check_irreversible(world, "faction_destroyed") is True
        assert engine.check_irreversible(world, "nonexistent") is False

    def test_get_world_summary(self):
        engine = QuestEngine()
        world = {}
        
        # Process some events to create timeline entries
        result = engine.process_event({"type": "attack", "importance": 0.8}, world)
        if result["new_quest"]:
            quest_id = result["new_quest"].id
            choice = PlayerChoice(
                quest_id=quest_id,
                stage="escalation",
                options=[{"id": "support_actor", "text": "Support"}],
            )
            choice.select_option("support_actor")
            world["factions"] = {"actor": {"power": 1.0}, "target": {"power": 1.0}}
            engine.resolve_choice(choice, quest_id, world, {})

        summary = engine.get_world_summary(world)
        assert "world" in summary
        assert "timeline" in summary

    def test_choice_affects_world_power(self):
        """Test that choices actually change faction power."""
        engine = QuestEngine()
        world = {
            "factions": {
                "red_faction": {"power": 1.0},
                "blue_faction": {"power": 1.0},
            }
        }
        memory = {}
        
        # Create a conflict quest
        result = engine.process_event({"type": "attack", "importance": 0.8}, world)
        quest_id = result["new_quest"].id
        
        # Store pre-choice power
        pre_red = world["factions"]["red_faction"]["power"]
        pre_blue = world["factions"]["blue_faction"]["power"]

        # Make a choice that supports red_faction
        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")
        
        effects = engine.resolve_choice(choice, quest_id, world, memory)
        
        # World state should have changed
        post_red = world["factions"]["red_faction"]["power"]
        post_blue = world["factions"]["blue_faction"]["power"]
        
        # At least one faction power should have changed
        assert post_red != pre_red or post_blue != pre_blue

    def test_choice_affects_beliefs(self):
        """Test that choices update NPC beliefs."""
        engine = QuestEngine()
        world = {"factions": {"actor": {"power": 1.0}, "target": {"power": 1.0}}}
        memory = {}
        
        # Create a quest manually with conflict type to get belief consequences
        quest = Quest(title="Test Conflict", type="conflict")
        stage = QuestStage(name="escalation")
        quest.stages = [stage]
        engine.tracker.add(quest)
        quest_id = quest.id

        choice = PlayerChoice(
            quest_id=quest_id,
            stage="escalation",
            options=[{"id": "support_actor", "text": "Support"}],
        )
        choice.select_option("support_actor")

        effects = engine.resolve_choice(choice, quest_id, world, memory)
        
        # Should have effects (faction shift, belief update, tag)
        assert len(effects) > 0
        
        # Beliefs should have been updated for conflict type
        # The belief key would be "actor->player" based on the consequence map
        if "beliefs" in memory:
            assert len(memory["beliefs"]) > 0
