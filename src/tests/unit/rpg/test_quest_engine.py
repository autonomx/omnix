"""Unit tests for the Quest Emergence Engine.

This module tests individual components of the quest system:
- Quest models (Quest, QuestStage, QuestObjective)
- Quest arc building from templates
- Quest state machine progression
- Quest detection from events
- Quest tracking management
- Quest director descriptions
- Full quest engine integration
"""

from typing import Any, Dict

import pytest

from app.rpg.quest.quest_arc_engine import QuestArcBuilder
from app.rpg.quest.quest_detector import QuestDetector
from app.rpg.quest.quest_director import QuestDirector
from app.rpg.quest.quest_engine import QuestEngine
from app.rpg.quest.quest_models import Quest, QuestObjective, QuestStage
from app.rpg.quest.quest_state_machine import QuestStateMachine
from app.rpg.quest.quest_templates import (
    QUEST_ARCS,
    get_arc_template,
    get_arc_type_for_quest,
)
from app.rpg.quest.quest_tracker import QuestTracker

# ==================== Quest Models Tests ====================

class TestQuestObjective:
    """Tests for QuestObjective model."""

    def test_create_objective(self):
        obj = QuestObjective(description="Test objective")
        assert obj.description == "Test objective"
        assert obj.progress == 0.0
        assert obj.completed is False
        assert obj.id is not None

    def test_update_progress(self):
        obj = QuestObjective()
        obj.update_progress(0.5)
        assert obj.progress == 0.5
        assert obj.completed is False

    def test_complete_objective(self):
        obj = QuestObjective()
        obj.update_progress(1.0)
        assert obj.progress == 1.0
        assert obj.completed is True

    def test_progress_caps_at_one(self):
        obj = QuestObjective()
        obj.update_progress(1.5)
        assert obj.progress == 1.0
        assert obj.completed is True

    def test_to_dict(self):
        obj = QuestObjective(description="Test")
        d = obj.to_dict()
        assert "id" in d
        assert d["description"] == "Test"
        assert d["progress"] == 0.0
        assert d["completed"] is False


class TestQuestStage:
    """Tests for QuestStage model."""

    def test_create_stage(self):
        stage = QuestStage(name="setup", description="Setup stage")
        assert stage.name == "setup"
        assert stage.description == "Setup stage"
        assert len(stage.objectives) == 0
        assert stage.world_effects == {}

    def test_all_completed_with_objectives(self):
        stage = QuestStage(name="test")
        obj1 = QuestObjective()
        obj2 = QuestObjective()
        obj1.update_progress(1.0)
        obj2.update_progress(1.0)
        stage.objectives = [obj1, obj2]
        assert stage.all_completed is True

    def test_all_completed_partial(self):
        stage = QuestStage(name="test")
        obj1 = QuestObjective()
        obj2 = QuestObjective()
        obj1.update_progress(1.0)
        stage.objectives = [obj1, obj2]
        assert stage.all_completed is False

    def test_all_completed_empty(self):
        stage = QuestStage(name="test")
        assert stage.all_completed is False

    def test_to_dict(self):
        stage = QuestStage(name="test", description="Desc")
        d = stage.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "Desc"
        assert d["objectives"] == []
        assert d["world_effects"] == {}


class TestQuest:
    """Tests for Quest model."""

    def test_create_quest(self):
        quest = Quest(title="Test Quest", type="conflict")
        assert quest.title == "Test Quest"
        assert quest.type == "conflict"
        assert quest.status == "active"
        assert quest.arc_stage == "setup"
        assert quest.arc_progress == 0.0
        assert quest.current_stage_index == 0

    def test_current_stage(self):
        quest = Quest()
        stage1 = QuestStage(name="setup")
        quest.stages = [stage1]
        assert quest.current_stage is stage1

    def test_current_stage_empty(self):
        quest = Quest()
        assert quest.current_stage is None

    def test_next_stage(self):
        quest = Quest()
        stage1 = QuestStage(name="setup")
        stage2 = QuestStage(name="escalation")
        quest.stages = [stage1, stage2]
        assert quest.next_stage is stage2

    def test_next_stage_last(self):
        quest = Quest()
        stage1 = QuestStage(name="setup")
        quest.stages = [stage1]
        assert quest.next_stage is None

    def test_active_objectives(self):
        quest = Quest()
        stage = QuestStage()
        obj1 = QuestObjective()
        obj2 = QuestObjective()
        obj1.update_progress(1.0)  # Complete
        stage.objectives = [obj1, obj2]
        quest.stages = [stage]
        assert len(quest.active_objectives) == 1
        assert quest.active_objectives[0] is obj2

    def test_complete(self):
        quest = Quest()
        quest.complete()
        assert quest.status == "completed"
        assert quest.arc_progress == 1.0
        assert quest.arc_stage == "completed"

    def test_fail(self):
        quest = Quest()
        quest.fail("Test reason")
        assert quest.status == "failed"
        assert len(quest.history) == 1
        assert quest.history[0]["action"] == "failed"

    def test_to_dict(self):
        quest = Quest(title="Test")
        d = quest.to_dict()
        assert d["title"] == "Test"
        assert d["status"] == "active"
        assert d["arc_stage"] == "setup"


# ==================== Quest Templates Tests ====================

class TestQuestTemplates:
    """Tests for quest templates."""

    def test_quest_arcs_has_conflict(self):
        assert "conflict" in QUEST_ARCS

    def test_quest_arcs_has_betrayal(self):
        assert "betrayal" in QUEST_ARCS

    def test_quest_arcs_has_supply(self):
        assert "supply" in QUEST_ARCS

    def test_quest_arcs_has_alliance(self):
        assert "alliance" in QUEST_ARCS

    def test_quest_arcs_has_rebellion(self):
        assert "rebellion" in QUEST_ARCS

    def test_conflict_arc_stages(self):
        stages = QUEST_ARCS["conflict"]
        assert len(stages) == 4
        assert stages[0]["name"] == "setup"
        assert stages[1]["name"] == "escalation"
        assert stages[2]["name"] == "climax"
        assert stages[3]["name"] == "resolution"

    def test_betrayal_arc_stages(self):
        stages = QUEST_ARCS["betrayal"]
        assert len(stages) == 4
        assert stages[0]["name"] == "setup"
        assert stages[2]["name"] == "confrontation"

    def test_get_arc_template(self):
        template = get_arc_template("conflict")
        assert len(template) == 4

    def test_get_arc_template_invalid(self):
        with pytest.raises(KeyError):
            get_arc_template("invalid")

    def test_get_arc_type_for_quest(self):
        assert get_arc_type_for_quest("war") == "conflict"
        assert get_arc_type_for_quest("betrayal") == "betrayal"
        assert get_arc_type_for_quest("supply") == "supply"
        assert get_arc_type_for_quest("alliance") == "alliance"
        assert get_arc_type_for_quest("rebellion") == "rebellion"
        assert get_arc_type_for_quest("unknown") == "conflict"


# ==================== Quest Arc Builder Tests ====================

class TestQuestArcBuilder:
    """Tests for QuestArcBuilder."""

    def test_build_conflict_arc(self):
        builder = QuestArcBuilder()
        event = {"type": "attack"}
        quest = builder.build_arc(event, "conflict")
        assert quest.type == "conflict"
        assert len(quest.stages) == 4
        assert quest.stages[0].name == "setup"
        assert quest.arc_stage == "setup"

    def test_build_betrayal_arc(self):
        builder = QuestArcBuilder()
        event = {"type": "betrayal"}
        quest = builder.build_arc(event, "betrayal")
        assert quest.type == "betrayal"
        assert len(quest.stages) == 4

    def test_build_arc_invalid_type(self):
        builder = QuestArcBuilder()
        with pytest.raises(KeyError):
            builder.build_arc({}, "invalid")

    def test_build_custom_arc(self):
        builder = QuestArcBuilder()
        custom_stages = [
            {"name": "start", "objectives": ["Do something"], "world_effects": {}},
            {"name": "end", "objectives": ["Finish"], "world_effects": {}},
        ]
        quest = builder.build_custom_arc({"type": "custom"}, "custom", custom_stages)
        assert len(quest.stages) == 2
        assert quest.stages[0].name == "start"

    def test_generate_title(self):
        builder = QuestArcBuilder()
        title = builder._generate_title("conflict", {"type": "attack"})
        assert "Attack" in title

    def test_get_stage_count(self):
        builder = QuestArcBuilder()
        assert builder.get_stage_count("conflict") == 4
        assert builder.get_stage_count("unknown") == 0


# ==================== Quest State Machine Tests ====================

class TestQuestStateMachine:
    """Tests for QuestStateMachine."""

    def test_advance_single_objective(self):
        sm = QuestStateMachine()
        quest = Quest()
        stage = QuestStage()
        quest.stages = [stage]
        world = {}
        for _ in range(5):
            progressed = sm.advance(quest, {"type": "test"}, world)
        assert stage.objectives or quest.current_stage_index >= len(quest.stages)

    def test_advance_inactive_quest(self):
        sm = QuestStateMachine()
        quest = Quest()
        quest.status = "completed"
        world = {}
        result = sm.advance(quest, {}, world)
        assert result is False

    def test_advance_no_stages(self):
        sm = QuestStateMachine()
        quest = Quest()
        world = {}
        result = sm.advance(quest, {}, world)
        assert result is False

    def test_force_advance(self):
        sm = QuestStateMachine()
        quest = Quest()
        stage = QuestStage(name="setup")
        stage.objectives = [QuestObjective(description="Test")]
        quest.stages = [stage, QuestStage(name="end")]
        world = {}
        sm.force_advance(quest, world)
        assert quest.current_stage_index == 1

    def test_reset_progress(self):
        sm = QuestStateMachine()
        quest = Quest()
        stage = QuestStage()
        obj = QuestObjective()
        obj.update_progress(0.5)
        stage.objectives = [obj]
        quest.stages = [stage]
        sm.reset_quest_progress(quest)
        assert obj.progress == 0.0
        assert obj.completed is False


# ==================== Quest Detector Tests ====================

class TestQuestDetector:
    """Tests for QuestDetector."""

    def test_detect_war(self):
        detector = QuestDetector()
        event = {"type": "attack", "importance": 0.8}
        quest = detector.detect(event)
        assert quest is not None
        assert quest.type == "war"

    def test_detect_betrayal(self):
        detector = QuestDetector()
        event = {"type": "betrayal", "importance": 0.7}
        quest = detector.detect(event)
        assert quest is not None
        assert quest.type == "betrayal"

    def test_detect_supply(self):
        detector = QuestDetector()
        event = {"type": "shortage", "importance": 0.6}
        quest = detector.detect(event)
        assert quest is not None
        assert quest.type == "supply"

    def test_detect_low_importance(self):
        detector = QuestDetector()
        event = {"type": "attack", "importance": 0.1}
        quest = detector.detect(event)
        assert quest is None

    def test_detect_empty_event(self):
        detector = QuestDetector()
        quest = detector.detect({})
        assert quest is None

    def test_detect_none(self):
        detector = QuestDetector()
        quest = detector.detect(None)
        assert quest is None

    def test_detect_unknown_type(self):
        detector = QuestDetector()
        event = {"type": "fishing", "importance": 0.8}
        quest = detector.detect(event)
        assert quest is None

    def test_is_quest_generating_event(self):
        detector = QuestDetector()
        assert detector.is_quest_generating_event({"type": "attack", "importance": 0.8})
        assert not detector.is_quest_generating_event({"type": "attack", "importance": 0.1})
        assert not detector.is_quest_generating_event({"type": "fishing"})


# ==================== Quest Tracker Tests ====================

class TestQuestTracker:
    """Tests for QuestTracker."""

    def test_add_quest(self):
        tracker = QuestTracker()
        quest = Quest(id="test1")
        result = tracker.add(quest)
        assert result is True
        assert len(tracker.get_active_quests()) == 1

    def test_add_duplicate(self):
        tracker = QuestTracker()
        quest = Quest(id="test1")
        tracker.add(quest)
        result = tracker.add(quest)
        assert result is False

    def test_add_limit(self):
        tracker = QuestTracker(max_active=2)
        tracker.add(Quest(id="q1"))
        tracker.add(Quest(id="q2"))
        result = tracker.add(Quest(id="q3"))
        assert result is False

    def test_complete_quest(self):
        tracker = QuestTracker()
        quest = Quest(id="test1")
        tracker.add(quest)
        completed = tracker.complete("test1")
        assert completed is quest
        assert completed.status == "completed"
        assert len(tracker.get_active_quests()) == 0
        assert len(tracker.get_completed_quests()) == 1

    def test_complete_not_found(self):
        tracker = QuestTracker()
        result = tracker.complete("notfound")
        assert result is None

    def test_fail_quest(self):
        tracker = QuestTracker()
        quest = Quest(id="test1")
        tracker.add(quest)
        failed = tracker.fail("test1", "Test reason")
        assert failed is not None
        assert failed.status == "failed"
        assert len(tracker.get_failed_quests()) == 1

    def test_get_quest(self):
        tracker = QuestTracker()
        quest = Quest(id="test1")
        tracker.add(quest)
        found = tracker.get_quest("test1")
        assert found is quest

    def test_get_quests_by_type(self):
        tracker = QuestTracker()
        q1 = Quest(id="q1", type="war")
        q2 = Quest(id="q2", type="supply")
        tracker.add(q1)
        tracker.add(q2)
        wars = tracker.get_quests_by_type("war")
        assert len(wars) == 1
        assert wars[0].id == "q1"

    def test_get_quests_by_status(self):
        tracker = QuestTracker()
        q1 = Quest(id="q1")
        tracker.add(q1)
        tracker.complete("q1")
        assert len(tracker.get_quests_by_status("completed")) == 1

    def test_has_active_quest_of_type(self):
        tracker = QuestTracker()
        q1 = Quest(id="q1", type="war")
        tracker.add(q1)
        assert tracker.has_active_quest_of_type("war") is True
        assert tracker.has_active_quest_of_type("supply") is False

    def test_get_stats(self):
        tracker = QuestTracker()
        stats = tracker.get_stats()
        assert "active" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "max_active" in stats

    def test_clear_completed(self):
        tracker = QuestTracker()
        q1 = Quest(id="q1")
        tracker.add(q1)
        tracker.complete("q1")
        count = tracker.clear_completed()
        assert count == 1
        assert len(tracker.get_completed_quests()) == 0

    def test_clear_failed(self):
        tracker = QuestTracker()
        q1 = Quest(id="q1")
        tracker.add(q1)
        tracker.fail("q1")
        count = tracker.clear_failed()
        assert count == 1


# ==================== Quest Director Tests ====================

class TestQuestDirector:
    """Tests for QuestDirector."""

    def test_generate_description(self):
        director = QuestDirector()
        quest = Quest(title="Test", type="conflict")
        stage = QuestStage(name="setup", description="Setup stage")
        stage.objectives = [QuestObjective(description="Do something")]
        quest.stages = [stage]
        desc = director.generate_description(quest)
        assert "Test" in desc
        assert "SETUP" in desc
        assert "Do something" in desc

    def test_generate_description_no_stages(self):
        director = QuestDirector()
        quest = Quest(title="Test")
        desc = director.generate_description(quest)
        assert "no stages" in desc

    def test_generate_summary(self):
        director = QuestDirector()
        quest = Quest(title="Test", type="conflict")
        stage = QuestStage(name="setup")
        quest.stages = [stage]
        summary = director.generate_summary(quest)
        assert summary["title"] == "Test"
        assert summary["type"] == "conflict"

    def test_generate_all_quests_description(self):
        director = QuestDirector()
        active = []
        result = director.generate_all_quests_description(active)
        assert "No active quests" in result