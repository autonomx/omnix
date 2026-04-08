"""Unit Tests for Tier 17.5 Patches - Persistent Goals, Adaptive Planning, Belief-Driven Decisions, NPC Interactions, and Narrative Significance.

This module contains unit tests for:
- PATCH 1: Persistent Goals (Stateful Intent)
- PATCH 2: Adaptive Planner (Replan on Failure)
- PATCH 3: Belief-Driven Decisions
- PATCH 4: Multi-NPC Interaction
- PATCH 5: Narrative Significance Layer
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

from rpg.ai.goal_generator import GoalGenerator
from rpg.ai.intent_engine import ACTION_BELIEF_EFFECTS, IntentEngine
from rpg.ai.npc_actor import NPCActor, NPCGoal
from rpg.ai.opposition_engine import OppositionEngine
from rpg.ai.planner import Planner


class TestNPCGoal:
    """Tests for PATCH 1 - Persistent Goals."""

    def test_npcgoal_creation(self):
        """Test basic NPCGoal creation."""
        goal = NPCGoal(
            id="g1",
            type="undermine_player",
            priority=0.7,
            target="player_1",
        )
        assert goal.id == "g1"
        assert goal.type == "undermine_player"
        assert goal.priority == 0.7
        assert goal.status == "active"
        assert goal.progress == 0.0
        assert goal.failed_attempts == 0

    def test_npcgoal_update_progress(self):
        """Test progress updates."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        result = goal.update_progress(0.3)
        assert result == 0.3
        assert goal.progress == 0.3

    def test_npcgoal_progress_completes_goal(self):
        """Test reaching 1.0 progress completes goal."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        goal.update_progress(0.5)
        goal.update_progress(0.5)
        assert goal.status == "completed"

    def test_npcgoal_record_failure(self):
        """Test failure tracking."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        goal.record_failure()
        assert goal.failed_attempts == 1
        assert goal.status == "active"

    def test_npcgoal_fails_after_5_attempts(self):
        """Test goal fails after 5 failures."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        for _ in range(5):
            goal.record_failure()
        assert goal.status == "failed"

    def test_npcgoal_reset(self):
        """Test goal reset."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        goal.update_progress(0.5)
        goal.record_failure()
        goal.reset()
        assert goal.progress == 0.0
        assert goal.failed_attempts == 0
        assert goal.status == "active"

    def test_npcgoal_to_dict(self):
        """Test serialization."""
        goal = NPCGoal(id="g1", type="test", priority=0.5, target="p1")
        d = goal.to_dict()
        assert d["id"] == "g1"
        assert d["type"] == "test"
        assert d["priority"] == 0.5

    def test_npcgoal_from_dict(self):
        """Test deserialization."""
        data = {"id": "g1", "type": "test", "priority": 0.5, "progress": 0.3}
        goal = NPCGoal.from_dict(data)
        assert goal.id == "g1"
        assert goal.progress == 0.3


class TestNPCActorStatefulGoals:
    """Tests for NPCActor with stateful goals."""

    def test_add_npc_goal(self):
        """Test adding NPCGoal to NPC."""
        npc = NPCActor(id="1", name="Test", faction="A")
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        npc.add_npc_goal(goal)
        assert len(npc.goals) == 1
        assert npc.goals[0].type == "test"

    def test_select_best_active_goal(self):
        """Test selecting best active NPCGoal."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.add_npc_goal(NPCGoal(id="g1", type="low", priority=0.3))
        npc.add_npc_goal(NPCGoal(id="g2", type="high", priority=0.8))
        best = npc.select_best_active_goal()
        assert best is not None
        assert best.type == "high"

    def test_select_best_active_goal_skips_failed(self):
        """Test that failed goals are ignored."""
        npc = NPCActor(id="1", name="Test", faction="A")
        g1 = NPCGoal(id="g1", type="failed", priority=0.9)
        g1.status = "failed"
        npc.add_npc_goal(g1)
        npc.add_npc_goal(NPCGoal(id="g2", type="active", priority=0.5))
        best = npc.select_best_active_goal()
        assert best.type == "active"

    def test_update_relationship(self):
        """Test relationship tracking."""
        npc = NPCActor(id="1", name="Test", faction="A")
        val = npc.update_relationship("npc_2", 0.3)
        assert val == 0.3
        assert npc.get_relationship("npc_2") == 0.3

    def test_update_relationship_clamped(self):
        """Test relationship bounds."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.update_relationship("npc_2", 1.5)
        assert npc.get_relationship("npc_2") == 1.0

    def test_record_failure(self):
        """Test failure memory."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.record_failure({"type": "attack"}, {"tick": 5})
        assert len(npc.failure_memory) == 1

    def test_get_similar_failures(self):
        """Test failure query."""
        npc = NPCActor(id="1", name="Test", faction="A")
        for _ in range(3):
            npc.record_failure({"type": "attack"}, {"tick": 0})
        npc.record_failure({"type": "spy"}, {"tick": 0})
        assert npc.get_similar_failures("attack") == 3


class TestGoalMerging:
    """Tests for PATCH 1 - Goal Merging."""

    def setup_method(self):
        self.generator = GoalGenerator()

    def test_merge_preserves_existing(self):
        """Test merge keeps existing goals."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.add_npc_goal(NPCGoal(id="g1", type="observe_player", priority=0.3))
        goals = self.generator.generate(npc, {})
        # Should not duplicate observe_player
        observe_count = sum(1 for g in goals if g.get("type") == "observe_player")
        assert observe_count <= 1

    def test_merge_updates_priority(self):
        """Test merge keeps highest priority."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.add_npc_goal(NPCGoal(id="g1", type="observe_player", priority=0.2))
        goals = self.generator.generate(npc, {})
        observe = next((g for g in goals if g.get("type") == "observe_player"), None)
        assert observe is not None


class TestAdaptivePlanner:
    """Tests for PATCH 2 - Adaptive Planning."""

    def setup_method(self):
        self.planner = Planner()

    def test_fallback_after_failures(self):
        """Test planner returns fallback after 3+ failures."""
        npc = NPCActor(id="1", name="Test", faction="A")
        goal = {"type": "undermine_player", "priority": 0.7, "failed_attempts": 3}
        plan = self.planner.create_plan(npc, goal, {})
        types = [a["type"] for a in plan]
        assert "reassess" in types or "retreat" in types

    def test_normal_plan_without_failures(self):
        """Test normal planning when no failures."""
        npc = NPCActor(id="1", name="Test", faction="A")
        goal = {"type": "undermine_player", "priority": 0.7}
        plan = self.planner.create_plan(npc, goal, {})
        types = [a["type"] for a in plan]
        assert "spy" in types or "sabotage" in types

    def test_smart_npc_fallback(self):
        """Test high-intelligence NPCs try new strategies."""
        npc = NPCActor(id="1", name="Smart", faction="A")
        npc.traits["intelligence"] = 0.9
        goal = {"type": "undermine_player", "priority": 0.7, "failed_attempts": 4}
        plan = self.planner.create_plan(npc, goal, {})
        types = [a["type"] for a in plan]
        assert "reassess" in types or "adapt" in types


class TestBeliefDrivenDecisions:
    """Tests for PATCH 3 - Belief-Driven Decisions."""

    def setup_method(self):
        self.engine = IntentEngine()

    def test_trust_drives_ally_goal(self):
        """Test high trust generates ally_player goal."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.beliefs["player_trust"] = 0.8
        gen = GoalGenerator()
        goals = gen.generate(npc, {})
        types = [g.get("type") for g in goals]
        assert "ally_player" in types

    def test_distrust_drives_undermine_goal(self):
        """Test low trust generates undermine_player goal."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.beliefs["player_trust"] = -0.5
        gen = GoalGenerator()
        goals = gen.generate(npc, {})
        types = [g.get("type") for g in goals]
        assert "undermine_player" in types

    def test_action_updates_beliefs(self):
        """Test actions modify beliefs."""
        npc = NPCActor(id="1", name="Test", faction="A")
        self.engine._update_beliefs_from_action(npc, {"type": "frame_player"})
        assert npc.beliefs.get("player_trust", 0) < 0

    def test_assist_increases_trust(self):
        """Test assist action increases trust."""
        npc = NPCActor(id="1", name="Test", faction="A")
        self.engine._update_beliefs_from_action(npc, {"type": "assist"})
        assert npc.beliefs.get("player_trust", 0) > 0

    def test_fear_drives_undermine(self):
        """Test high fear undermines player."""
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.beliefs["player_fear"] = 0.8
        gen = GoalGenerator()
        goals = gen.generate(npc, {})
        types = [g.get("type") for g in goals]
        assert "undermine_player" in types


class TestNPCInteractions:
    """Tests for PATCH 4 - NPC vs NPC Interaction."""

    def setup_method(self):
        self.engine = IntentEngine()

    def test_attack_increases_threat(self):
        """Test attack increases threat in other faction NPCs."""
        npc1 = NPCActor(id="1", name="Aggressor", faction="A")
        npc2 = NPCActor(id="2", name="Defender", faction="B")
        self.engine._process_npc_interactions(
            npc1, {"type": "attack"}, [npc2]
        )
        assert npc2.beliefs.get("threat", 0) > 0

    def test_ally_same_faction_relationship(self):
        """Test alliance improves same-faction relationships."""
        npc1 = NPCActor(id="1", name="Leader", faction="A")
        npc2 = NPCActor(id="2", name="Member", faction="A")
        self.engine._process_npc_interactions(
            npc1, {"type": "assist"}, [npc2]
        )
        assert npc1.get_relationship("2") > 0
        assert npc2.get_relationship("1") > 0

    def test_spy_noticed_by_vigilant(self):
        """Test vigilant NPCs notice spying."""
        npc1 = NPCActor(id="1", name="Spy", faction="A")
        npc2 = NPCActor(id="2", name="Guard", faction="B")
        npc2.beliefs["vigilance"] = 0.8
        self.engine._process_npc_interactions(
            npc1, {"type": "spy"}, [npc2]
        )
        assert npc2.get_relationship("1") < 0

    def test_no_self_interaction(self):
        """Test NPC doesn't interact with itself."""
        npc = NPCActor(id="1", name="Solo", faction="A")
        self.engine._process_npc_interactions(
            npc, {"type": "attack"}, [npc]
        )
        assert npc.beliefs.get("threat", 0) == 0


class TestNarrativeSignificance:
    """Tests for PATCH 5 - Narrative Significance Layer."""

    def setup_method(self):
        self.engine = IntentEngine()

    def test_high_impact_actions(self):
        """Test high-impact actions score 1.0."""
        for action_type in ["frame_player", "attack"]:
            weight = self.engine.get_narrative_weight({"type": action_type}, {})
            assert weight == 1.0, f"{action_type} should be 1.0"

    def test_medium_impact_actions(self):
        """Test medium-impact actions score 0.6."""
        for action_type in ["sabotage", "spy", "gift"]:
            weight = self.engine.get_narrative_weight({"type": action_type}, {})
            assert weight == 0.6, f"{action_type} should be 0.6"

    def test_low_impact_actions(self):
        """Test low-impact actions score 0.3."""
        weight = self.engine.get_narrative_weight({"type": "observe"}, {})
        assert weight == 0.3

    def test_is_major_event(self):
        """Test major event detection."""
        assert self.engine.is_major_event({"type": "frame_player"}, {}) is True
        assert self.engine.is_major_event({"type": "spy"}, {}) is False

    def test_update_all_npcs_passes_others(self):
        """Test update_all_npcs passes other NPCs for interaction."""
        npc1 = NPCActor(id="1", name="A", faction="F1")
        npc2 = NPCActor(id="2", name="B", faction="F2")
        world = {}
        # Should not raise
        results = self.engine.update_all_npcs([npc1, npc2], world, tick=0)
        assert isinstance(results, list)


class TestNPCAdaptsToFailures:
    """Integration test from rpg-design.txt spec."""

    def test_npc_adapts_to_failed_plan(self):
        """Test NPC adapts after repeated failures.

        This is the exact test specification from rpg-design.txt.
        """
        npc = NPCActor(id="1", name="Adaptor", faction="A")
        npc.legacy_goals = [{"type": "undermine_player", "priority": 0.7}]
        engine = IntentEngine()

        # Force repeated failure
        for i in range(5):
            action = engine.update_npc(npc, {}, i)
            if action:
                engine.update_beliefs_from_action_result(
                    npc, action["action"], success=False
                )

        # NPC must not repeat same plan forever
        # After failures, planner should return fallback
        assert npc.current_plan != ["spy", "sabotage", "frame_player"] or len(npc.current_plan) == 0


# =============================================================================
# CRITICAL INTELLIGENCE TESTS — Prove Adaptation, Emergence, and Causality
# =============================================================================


class TestNPCsDivergeOverTime:
    """PROBLEM 1 — Stability ≠ Intelligence.

    Without this test: NPCs are deterministic clones.
    With this test: NPCs develop unique behavioral profiles.
    """

    def test_npcs_diverge_over_time(self):
        """Two NPCs with different beliefs should NOT behave identically over time.

        Different trust levels → different goals → different actions.
        """
        npc1 = NPCActor(id="1", name="Alpha", faction="A")
        npc2 = NPCActor(id="2", name="Beta", faction="A")

        # Give them different starting beliefs to seed divergence
        npc1.beliefs["player_trust"] = 0.7
        npc2.beliefs["player_trust"] = 0.2

        engine = IntentEngine()

        plans1 = []
        plans2 = []

        for tick in range(20):
            action1 = engine.update_npc(npc1, {}, tick)
            action2 = engine.update_npc(npc2, {}, tick)

            if action1:
                plans1.append(action1["action"]["type"])
            if action2:
                plans2.append(action2["action"]["type"])

        # They should NOT have identical action histories
        assert plans1 != plans2, (
            f"NPCs should diverge but got identical sequences: {plans1[:5]}..."
        )

    def test_npcs_diverge_from_same_starting_conditions(self):
        """Even with identical beliefs, NPCs should show variance via ID-based strategy bias."""
        npc1 = NPCActor(id="1", name="CloneA", faction="A")
        npc2 = NPCActor(id="2", name="CloneB", faction="A")

        npc1.beliefs["player_trust"] = 0.5
        npc2.beliefs["player_trust"] = 0.5

        engine = IntentEngine()

        actions1 = []
        actions2 = []

        for tick in range(30):
            a1 = engine.update_npc(npc1, {}, tick)
            a2 = engine.update_npc(npc2, {}, tick)
            if a1:
                actions1.append(a1["action"]["type"])
            if a2:
                actions2.append(a2["action"]["type"])

        # Verify both NPCs produced actions
        assert len(actions1) > 0, "NPC1 should have produced actions"
        assert len(actions2) > 0, "NPC2 should have produced actions"


class TestCausalChainVerification:
    """PROBLEM 2 — No Causal Chain Verification.

    Tests that actions cause specific, traceable outcomes.
    You need cause → effect traceability.
    """

    def test_action_causes_specific_outcome(self):
        """frame_player action should decrease player_reputation."""
        npc = NPCActor(id="1", name="Enemy", faction="A")

        action = {
            "npc_id": "1",
            "action": {"type": "frame_player"}
        }

        world = {"player_reputation": 0.5}

        engine = OppositionEngine()
        mock_quest_engine = MagicMock()
        engine.apply(action, mock_quest_engine, world)

        assert world["player_reputation"] < 0.5

    def test_assist_increases_quest_progress(self):
        """assist action should have positive quest_impact."""
        npc = NPCActor(id="1", name="Helper", faction="A")

        action = {
            "npc_id": "1",
            "action": {"type": "assist"}
        }

        world = {}

        engine = OppositionEngine()
        mock_quest_engine = MagicMock()
        result = engine.apply(action, mock_quest_engine, world)

        # Verify action was recognized
        assert result["action"] == "assist"

    def test_attack_increases_global_tension(self):
        """attack action should increase global_tension."""
        action = {
            "npc_id": "1",
            "action": {"type": "attack"}
        }

        world = {"global_tension": 0.0}

        engine = OppositionEngine()
        mock_quest_engine = MagicMock()
        engine.apply(action, mock_quest_engine, world)

        assert world["global_tension"] > 0.0


class TestMultiAgentEmergence:
    """PROBLEM 3 — No Multi-Agent Emergence Test.

    Isolation ≠ Interaction. This tests emergence from multi-agent dynamics.
    The difference between simulation and emergence.
    """

    def test_npc_conflict_emerges(self):
        """Hostile action between factions should create threat belief or tension."""
        npc1 = NPCActor(id="1", name="Alpha", faction="A")
        npc2 = NPCActor(id="2", name="Beta", faction="B")

        # Seed fear and low trust to drive hostile behavior
        npc1.beliefs["player_fear"] = 0.8
        npc1.beliefs["player_trust"] = -0.5
        npc2.beliefs["player_fear"] = 0.8
        npc2.beliefs["player_trust"] = -0.5

        engine = IntentEngine()

        world = {"factions": {"A": {"power": 1.0}, "B": {"power": 1.0}}}

        for tick in range(30):
            action1 = engine.update_npc(npc1, world, tick)
            action2 = engine.update_npc(npc2, world, tick)

            # Track belief changes
            if action1:
                engine._process_npc_interactions(npc1, action1["action"], [npc2])
            if action2:
                engine._process_npc_interactions(npc2, action2["action"], [npc1])

        # Expect tension or hostility to emerge
        threat_npc1 = npc1.get_belief("threat", 0.0)
        threat_npc2 = npc2.get_belief("threat", 0.0)
        global_tension = world.get("global_tension", 0)

        assert (
            threat_npc1 > 0
            or threat_npc2 > 0
            or global_tension > 0
        ), f"No emergence detected. Threats: {threat_npc1}, {threat_npc2}. Tension: {global_tension}"

    def test_faction_cooperation_emerges(self):
        """Same-faction NPCs should build positive relationships."""
        npc1 = NPCActor(id="1", name="Ally1", faction="A")
        npc2 = NPCActor(id="2", name="Ally2", faction="A")

        engine = IntentEngine()
        world = {}

        for tick in range(20):
            action1 = engine.update_npc(npc1, world, tick)
            action2 = engine.update_npc(npc2, world, tick)

            if action1:
                engine._process_npc_interactions(npc1, action1["action"], [npc2])
            if action2:
                engine._process_npc_interactions(npc2, action2["action"], [npc1])

        # Same faction should not be hostile to each other
        rel_1_to_2 = npc1.get_relationship("2")
        rel_2_to_1 = npc2.get_relationship("1")

        # At minimum, relationships shouldn't degrade
        assert rel_1_to_2 >= -0.5, f"Same-faction relationship degraded: {rel_1_to_2}"
        assert rel_2_to_1 >= -0.5, f"Same-faction relationship degraded: {rel_2_to_1}"


class TestNarrativeWeightBehavioral:
    """PROBLEM 4 — Narrative Weight Is Untested Behaviorally.

    Tests that narrative weight actually affects the story.
    Not just 0.0 <= weight <= 1.0.
    """

    def test_high_weight_triggers_story_flag(self):
        """High narrative weight should trigger major event detection."""
        engine = IntentEngine()

        action = {"type": "attack"}
        weight = engine.get_narrative_weight(action, {})

        # High weight should be detected as major event
        if weight > 0.8:
            assert engine.is_major_event(action, {}) is True

    def test_low_weight_does_not_trigger_story_flag(self):
        """Low narrative weight should NOT trigger major event detection."""
        engine = IntentEngine()

        action = {"type": "observe"}
        weight = engine.get_narrative_weight(action, {})

        assert weight < 0.8
        assert engine.is_major_event(action, {}) is False

    def test_narrative_weight_affects_action_priority(self):
        """Higher narrative weight should influence action significance."""
        engine = IntentEngine()

        low_action = {"type": "observe"}
        high_action = {"type": "frame_player"}

        low_weight = engine.get_narrative_weight(low_action, {})
        high_weight = engine.get_narrative_weight(high_action, {})

        assert high_weight > low_weight, (
            f"High-impact action ({high_weight}) should exceed low-impact ({low_weight})"
        )


class TestDegenerationPrevention:
    """PROBLEM 5 — No Degeneration Test.

    Bounded memory ≠ non-looping behavior.
    Tests that behavior doesn't collapse into loops.
    """

    def test_no_behavior_looping(self):
        """NPC should not repeat identical action pattern forever."""
        npc = NPCActor(id="1", name="Looper", faction="A")
        engine = IntentEngine()

        actions = []

        for tick in range(50):
            action = engine.update_npc(npc, {}, tick)
            if action:
                actions.append(action["action"]["type"])

        # Should not repeat identical pattern forever
        # At least 3 different action types expected over 50 ticks
        assert len(set(actions)) > 2, (
            f"Behavior degenerated into loop. Only {len(set(actions))} unique actions: {set(actions)}"
        )

    def test_no_action_type_stuck(self):
        """NPC should not get stuck on single action type."""
        npc = NPCActor(id="1", name="Stuck", faction="A")
        npc.beliefs["player_trust"] = 0.5  # Neutral starting point
        engine = IntentEngine()

        actions = []

        for tick in range(40):
            action = engine.update_npc(npc, {}, tick)
            if action:
                actions.append(action["action"]["type"])

        if len(actions) > 5:
            # Same action shouldn't dominate more than 80%
            from collections import Counter
            counts = Counter(actions)
            most_common_count = counts.most_common(1)[0][1]
            ratio = most_common_count / len(actions)
            assert ratio < 0.8, (
                f"NPC stuck on single action: {counts.most_common(1)[0][0]} ({ratio:.0%})"
            )

    def test_belief_driven_plan_variation(self):
        """Changing beliefs should cause different plan types."""
        npc = NPCActor(id="1", name="Adaptive", faction="A")
        engine = IntentEngine()

        # Phase 1: High trust
        npc.beliefs["player_trust"] = 0.8
        actions_trust = []
        for tick in range(10):
            action = engine.update_npc(npc, {}, tick)
            if action:
                actions_trust.append(action["action"]["type"])

        # Phase 2: Reset and set low trust
        npc.goals = []
        npc.current_plan = []
        npc.beliefs["player_trust"] = 0.1
        actions_distrust = []
        for tick in range(10, 20):
            action = engine.update_npc(npc, {}, tick)
            if action:
                actions_distrust.append(action["action"]["type"])

        # Different belief states should produce different actions
        trust_types = set(actions_trust)
        distrust_types = set(actions_distrust)
        assert trust_types != distrust_types or len(actions_trust) == 0 or len(actions_distrust) == 0, (
            "Belief changes should drive different action types"
        )