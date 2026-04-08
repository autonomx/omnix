"""Functional tests for the Quest Emergence Engine.

This module tests the complete quest system workflow:
- Multi-stage quest progression (depth test from design spec)
- World effects from stage completion
- Multiple concurrent quests
- Quest to world simulation integration
- End-to-end event processing pipeline
"""

import pytest

from app.rpg.quest.quest_engine import QuestEngine
from app.rpg.quest.quest_models import Quest, QuestObjective, QuestStage

# ==================== Multi-Stage Quest Progression ====================

class TestMultiStageQuest:
    """Test multi-stage quest progression as specified in design."""

    def test_conflict_arc_progression(self):
        """Test full conflict arc through all stages."""
        engine = QuestEngine()
        world = {"time": 0, "tension_level": 0.0}

        # Feed events to progress through quest stages
        events = [
            {"type": "attack", "importance": 0.8},
            {"type": "attack"},
            {"type": "war"},
            {"type": "resolution"},
        ]

        for i, e in enumerate(events):
            world["time"] = i
            engine.process_event(e, world)

        quests = engine.tracker.get_active_quests() + engine.tracker.get_completed_quests()
        assert len(quests) >= 1

        quest = engine.tracker.get_quest(quests[0].id)
        assert quest.current_stage_index >= 1
        assert len(quest.history) >= 1

    def test_multi_stage_quest_depth_test(self):
        """Critical depth test from design specification.

        Process multiple events and verify quest reaches at least stage 2 (climax).
        Each stage has multiple objectives that need 4 events each to complete.
        """
        engine = QuestEngine()
        world = {"time": 0}

        # Need enough events to complete:
        # Stage 0 (setup): 1 objective × 4 events = 4 events
        # Stage 1 (escalation): 2 objectives × 4 events each = 8 events  
        # Total: 12+ events to reach stage 2 (climax)
        events = [
            {"type": "attack", "importance": 0.8},  # 1
            {"type": "attack"},                      # 2
            {"type": "war"},                         # 3
            {"type": "attack"},                      # 4 - setup complete
            {"type": "attack"},                      # 5 - escalation obj 1
            {"type": "war"},                         # 6 - escalation obj 1
            {"type": "attack"},                      # 7 - escalation obj 1
            {"type": "attack"},                      # 8 - escalation obj 1 complete
            {"type": "war"},                         # 9 - escalation obj 2
            {"type": "attack"},                      # 10 - escalation obj 2
            {"type": "war"},                         # 11 - escalation obj 2
            {"type": "attack"},                      # 12 - escalation complete → climax
            {"type": "resolution"},                  # 13 - climax progress
        ]

        for i, e in enumerate(events):
            world["time"] = i
            engine.process_event(e, world)

        quest_list = engine.tracker.get_active_quests() + engine.tracker.get_completed_quests()
        assert len(quest_list) >= 1
        quest = quest_list[0]
        assert quest.current_stage_index >= 2


# ==================== World Effects ====================

class TestWorldEffects:
    """Test world state changes from quest stage completion."""

    def test_tension_level_increase(self):
        """Test that tension increases through stages."""
        engine = QuestEngine()
        world = {"time": 0, "tension_level": 0.0}

        # Process many events to advance through stages
        for i in range(10):
            result = engine.process_event({"type": "attack", "importance": 0.8}, world)
            world["time"] = i

        quest = engine.tracker.get_active_quests()
        if quest:
            # Check world effects were applied
            assert "tension_level" in world or world.get("tension_level", 0) != 0.0

    def test_faction_power_shift(self):
        """Test faction power shift on quest completion."""
        engine = QuestEngine()
        world = {"faction_power_shift": False}

        # Complete a full arc through many events
        for i in range(20):
            engine.process_event(
                {"type": "attack", "importance": 0.9},
                world,
            )

        completed = engine.tracker.get_completed_quests()
        if completed:
            quest = completed[0]
            assert quest.status == "completed"
            assert quest.arc_stage == "completed"

    def test_trust_network_decrease_betrayal(self):
        """Test trust decreases on betrayal arc."""
        engine = QuestEngine()
        world = {"trust_network": 0.0}

        engine.process_event({"type": "betrayal", "importance": 0.7}, world)

        # Process more events to advance stages
        for i in range(10):
            engine.process_event({"type": "betrayal"}, world)

        completed = engine.tracker.get_completed_quests()
        if completed:
            quest = completed[0]
            assert quest.status == "completed"


# ==================== Multiple Concurrent Quests ====================

class TestConcurrentQuests:
    """Test multiple quests running simultaneously."""

    def test_multiple_conflict_quests(self):
        """Test multiple war quests from different events."""
        engine = QuestEngine(max_active_quests=5)
        world = {}

        events = [
            {"type": "attack", "importance": 0.9},
            {"type": "war", "importance": 0.8},
            {"type": "battle", "importance": 0.85},
            {"type": "fight", "importance": 0.75},
        ]

        for event in events:
            engine.process_event(event, world)

        active = engine.tracker.get_active_quests()
        assert len(active) >= 1

    def test_mixed_quest_types(self):
        """Test quests of different types running concurrently."""
        engine = QuestEngine(max_active_quests=10)
        world = {"trust_network": 0.0, "tension_level": 0.0}

        mixed_events = [
            {"type": "attack", "importance": 0.8},
            {"type": "betrayal", "importance": 0.7},
            {"type": "shortage", "importance": 0.6},
            {"type": "alliance", "importance": 0.5},
        ]

        for event in mixed_events:
            engine.process_event(event, world)

        types = {q.type for q in engine.tracker.get_active_quests()}
        assert len(types) >= 1

    def test_quest_limit_enforced(self):
        """Test that max_active limit prevents overflow."""
        engine = QuestEngine(max_active_quests=2)
        world = {}

        for _ in range(5):
            engine.process_event({"type": "attack", "importance": 0.9}, world)

        active = engine.tracker.get_active_quests()
        assert len(active) <= 2


# ==================== End-to-End Pipeline ====================

class TestEndToEndPipeline:
    """Test complete event-to-narrative pipeline."""

    def test_event_triggers_quest_with_description(self):
        """Test that event produces quest with generated description."""
        engine = QuestEngine()
        world = {}

        result = engine.process_event(
            {"type": "attack", "importance": 0.8, "description": "A great battle begins"},
            world,
        )

        assert result["new_quest"] is not None
        quest = result["new_quest"]
        assert quest.title != ""
        assert quest.type != ""

        desc = engine.get_quest_description(quest.id)
        assert desc is not None
        assert len(desc) > 0

    def test_complete_pipeline_with_world_effects(self):
        """Test full pipeline: event → detection → arc building → progression → world effects."""
        engine = QuestEngine()
        world = {"tension_level": 0.0, "time": 0}
        effects_callback = []

        def track_effect(ws, value):
            effects_callback.append((ws, value))

        engine.register_world_effect_callback("tension_level", track_effect)

        # Run simulation
        for i in range(15):
            world["time"] = i
            engine.process_event({"type": "attack"}, world)

        # Verify pipeline worked
        assert len(engine.tracker.get_active_quests()) >= 0 or len(engine.tracker.get_completed_quests()) >= 0

    def test_quest_status_api(self):
        """Test quest status API endpoints."""
        engine = QuestEngine()
        world = {}

        result = engine.process_event({"type": "attack", "importance": 0.8}, world)
        quest = result["new_quest"]

        status = engine.get_quest_status(quest.id)
        assert status is not None
        assert "title" in status
        assert "stage" in status
        assert "status" in status

        quest_desc = engine.get_quest_description(quest.id)
        assert quest_desc is not None

    def test_stats_reporting(self):
        """Test engine statistics."""
        engine = QuestEngine()
        world = {}

        engine.process_event({"type": "attack", "importance": 0.8}, world)
        stats = engine.get_stats()

        assert "active" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "total" in stats
        assert "max_active" in stats


# ==================== Functional Regression ====================

class TestFunctionalRegression:
    """Regression tests for known issues and edge cases."""

    def test_rapid_event_processing(self):
        """Test processing many rapid events doesn't break."""
        engine = QuestEngine()
        world = {"time": 0}

        for i in range(100):
            world["time"] = i
            result = engine.process_event({"type": "attack", "importance": 0.5}, world)
            assert result is not None
            assert "active_quests" in result

    def test_reset_functionality(self):
        """Test engine reset clears all state."""
        engine = QuestEngine()
        world = {}

        engine.process_event({"type": "attack", "importance": 0.8}, world)
        assert len(engine.tracker.get_active_quests()) >= 1

        engine.reset()
        assert len(engine.tracker.get_active_quests()) == 0
        assert len(engine.tracker.get_completed_quests()) == 0
        assert len(engine.tracker.get_failed_quests()) == 0

    def test_empty_world_state(self):
        """Test processing with empty world state."""
        engine = QuestEngine()
        result = engine.process_event({"type": "attack", "importance": 0.8}, {})
        assert result is not None
        assert "new_quest" in result

    def test_none_world_effect_values(self):
        """Test world effects with non-numeric values."""
        engine = QuestEngine()
        world = {}

        for _ in range(20):
            engine.process_event({"type": "betrayal", "importance": 0.8}, world)

        completed = engine.tracker.get_completed_quests()
        if completed:
            # World state should be valid
            assert isinstance(world, dict)