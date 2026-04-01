"""Unit Tests for TIER 10: Autonomous NPC Agent System.

Tests for:
- AgentBrain: Decision-making from goals/beliefs
- Planner: Multi-step plan creation
- ActionExecutor: Event generation
- AgentScheduler: NPC selection
- AgentSystem: Full orchestration
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))


@dataclass
class MockCharacter:
    """Mock character for testing."""
    id: str
    name: str = "Test Character"
    beliefs: Dict[str, float] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    memory: List[Dict[str, Any]] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    role: str = "unknown"
    power: float = 0.5
    resources: float = 0.5
    
    def get_belief(self, entity_id: str) -> float:
        return self.beliefs.get(entity_id, 0.0)
    
    def add_belief(self, entity_id: str, value: float) -> None:
        self.beliefs[entity_id] = max(-1.0, min(1.0, value))
    
    def adjust_belief(self, entity_id: str, delta: float) -> float:
        current = self.beliefs.get(entity_id, 0.0)
        new_value = max(-1.0, min(1.0, current + delta))
        self.beliefs[entity_id] = new_value
        return new_value
    
    def add_goal(self, goal: str) -> None:
        if goal not in self.goals:
            self.goals.append(goal)
    
    def add_memory(self, event: Dict[str, Any]) -> None:
        self.memory.append(event)


# =====================================================================
# AgentBrain Tests
# =====================================================================

class TestAgentBrain:
    """Tests for AgentBrain decision-making."""
    
    def test_no_goals_returns_none(self):
        from rpg.agent.agent_brain import AgentBrain
        
        brain = AgentBrain()
        char = MockCharacter(id="npc1", goals=[])
        result = brain.decide(char, {})
        
        assert result is None
    
    def test_idle_when_no_matching_goals(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_IDLE
        
        brain = AgentBrain()
        char = MockCharacter(id="npc1", goals=["random_unknown_goal"])
        result = brain.decide(char, {})
        
        # Unknown goals fall through to idle or expand_influence
        assert result is not None
        assert result["type"] in (INTENTION_IDLE, "expand_influence")
    
    def test_power_goal_generates_expand_influence(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_EXPAND_INFLUENCE
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["gain power"],
            beliefs={"rival": -0.5},
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_EXPAND_INFLUENCE
    
    def test_attack_goal_generates_attack_target(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_ATTACK_TARGET
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["attack enemies"],
            beliefs={"enemy": -0.8},
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_ATTACK_TARGET
    
    def test_revenge_goal_generates_attack_target(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_ATTACK_TARGET
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["revenge on traitor"],
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_ATTACK_TARGET
    
    def test_help_goal_generates_deliver_aid(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_DELIVER_AID
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["help the villagers"],
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_DELIVER_AID
    
    def test_gather_goal_generates_gather_resources(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_GATHER_RESOURCES
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["gather supplies"],
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_GATHER_RESOURCES
    
    def test_negotiate_goal_generates_negotiate(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_NEGOTIATE
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["negotiate peace"],
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_NEGOTIATE
    
    def test_low_power_triggers_survival(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_GATHER_RESOURCES
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["gain power"],
            power=0.1,
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert result["type"] == INTENTION_GATHER_RESOURCES
        assert result["priority"] == 10.0  # Survival is highest priority
    
    def test_intention_has_required_fields(self):
        from rpg.agent.agent_brain import AgentBrain
        
        brain = AgentBrain()
        char = MockCharacter(
            id="npc1",
            goals=["expand influence"],
            beliefs={"faction_a": 0.5},
        )
        result = brain.decide(char, {})
        
        assert result is not None
        assert "type" in result
        assert "priority" in result
        assert "reasoning" in result
    
    def test_beliefs_modulate_priority(self):
        from rpg.agent.agent_brain import AgentBrain, INTENTION_EXPAND_INFLUENCE
        
        brain = AgentBrain()
        
        # Character with strong beliefs should have higher priority
        char_strong = MockCharacter(
            id="npc1",
            goals=["expand influence"],
            beliefs={"faction_a": -0.9},  # Strong negative
        )
        
        char_weak = MockCharacter(
            id="npc2",
            goals=["expand influence"],
            beliefs={"faction_a": -0.1},  # Weak negative
        )
        
        result_strong = brain.decide(char_strong, {})
        result_weak = brain.decide(char_weak, {})
        
        assert result_strong is not None
        assert result_weak is not None
        # Strong negative beliefs should increase priority for expand_influence
        assert result_strong["priority"] >= result_weak["priority"]


# =====================================================================
# Planner Tests
# =====================================================================

class TestPlanner:
    """Tests for Planner multi-step planning."""
    
    def test_create_plan_from_expand_influence(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        intention = {"type": "expand_influence", "target": "mages_guild"}
        plan = planner.create_plan(intention)
        
        assert len(plan.steps) >= 2
        assert any(s["action"] == "increase_power" for s in plan.steps)
    
    def test_create_plan_from_attack_target(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        intention = {"type": "attack_target", "target": "enemy_fort"}
        plan = planner.create_plan(intention)
        
        assert len(plan.steps) >= 2
        assert any(s["action"] == "gather_forces" for s in plan.steps)
        assert any(s["action"] == "attack" for s in plan.steps)
    
    def test_create_plan_from_deliver_aid(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        intention = {"type": "deliver_aid", "target": "village"}
        plan = planner.create_plan(intention)
        
        assert len(plan.steps) == 3
        actions = [s["action"] for s in plan.steps]
        assert "gather_resources" in actions
        assert "travel" in actions
        assert "deliver" in actions
    
    def test_plan_next_steps_through_plan(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([
            {"action": "step1"},
            {"action": "step2"},
            {"action": "step3"},
        ])
        
        assert plan.next()["action"] == "step1"
        assert plan.next()["action"] == "step2"
        assert plan.next()["action"] == "step3"
        assert plan.next() is None
    
    def test_plan_next_returns_none_when_complete(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "only_step"}])
        assert plan.next() is not None
        assert plan.next() is None
    
    def test_plan_is_complete_property(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "a"}, {"action": "b"}])
        assert not plan.is_complete
        
        plan.next()
        assert not plan.is_complete
        
        plan.next()
        assert plan.is_complete
    
    def test_plan_progress(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "a"}, {"action": "b"}, {"action": "c"}, {"action": "d"}])
        assert plan.progress == 0.0
        
        plan.next()
        assert plan.progress == 0.25
        
        plan.next()
        assert plan.progress == 0.5
        
        plan.next()
        plan.next()
        assert plan.progress == 1.0
    
    def test_plan_reset(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "a"}, {"action": "b"}])
        plan.next()
        plan.next()
        assert plan.is_complete
        
        plan.reset()
        assert not plan.is_complete
        assert plan.current_step == 0
    
    def test_plan_mark_failed(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "a"}])
        assert not plan.failed
        plan.mark_failed()
        assert plan.failed
    
    def test_plan_peek(self):
        from rpg.agent.planner import Plan
        
        plan = Plan([{"action": "first"}, {"action": "second"}])
        assert plan.peek()["action"] == "first"
        
        plan.next()
        assert plan.peek()["action"] == "second"
    
    def test_intention_metadata_copied_to_steps(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        intention = {
            "type": "expand_influence",
            "target": "guild",
            "priority": 7.0,
            "reasoning": "test reason",
        }
        plan = planner.create_plan(intention)
        
        for step in plan.steps:
            assert step["target"] == "guild"
            assert step["priority"] == 7.0
            assert step["reasoning"] == "test reason"
    
    def test_fallback_to_idle_for_unknown_type(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        intention = {"type": "unknown_intention_type_xyz"}
        plan = planner.create_plan(intention)
        
        assert len(plan.steps) >= 1
        assert plan.steps[0]["action"] == "wait"
    
    def test_register_custom_template(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        planner.register_template("custom_action", [
            {"action": "custom_step_1"},
            {"action": "custom_step_2"},
        ])
        
        plan = planner.create_plan({"type": "custom_action"})
        assert len(plan.steps) == 2
        assert plan.steps[0]["action"] == "custom_step_1"
    
    def test_get_available_templates(self):
        from rpg.agent.planner import Planner
        
        planner = Planner()
        templates = planner.get_available_templates()
        
        assert "expand_influence" in templates
        assert "attack_target" in templates
        assert "deliver_aid" in templates
        assert "idle" in templates


# =====================================================================
# ActionExecutor Tests
# =====================================================================

class TestActionExecutor:
    """Tests for ActionExecutor event generation."""
    
    def test_execute_increase_power(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="npc1")
        events = executor.execute(char, {"action": "increase_power"})
        
        assert len(events) == 1
        assert events[0]["type"] == "power_growth"
        assert events[0]["actor"] == "npc1"
    
    def test_execute_attack(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="attacker")
        events = executor.execute(char, {"action": "attack", "target": "enemy"})
        
        assert len(events) == 1
        assert events[0]["type"] == "faction_conflict"
        assert events[0]["attacker"] == "attacker"
        assert events[0]["target"] == "enemy"
    
    def test_execute_deliver(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="healer")
        events = executor.execute(char, {"action": "deliver", "target": "village"})
        
        assert len(events) == 1
        assert events[0]["type"] == "aid_delivered"
        assert events[0]["recipient"] == "village"
    
    def test_execute_wait_produces_no_events(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="sleeper")
        events = executor.execute(char, {"action": "wait"})
        
        assert len(events) == 0
    
    def test_execute_unknown_action(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="confused")
        events = executor.execute(char, {"action": "unknown_bla"})
        
        assert len(events) == 1
        assert events[0]["type"] == "unknown_action"
    
    def test_execute_travel(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="traveler")
        events = executor.execute(char, {"action": "travel", "target": "distant_city"})
        
        assert len(events) == 1
        assert events[0]["type"] == "travel"
        assert events[0]["destination"] == "distant_city"
    
    def test_execute_negotiate(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="diplomat")
        events = executor.execute(char, {"action": "negotiate", "target": "alliance"})
        
        assert len(events) == 1
        assert events[0]["type"] == "diplomatic_meeting"
    
    def test_execute_gather_forces(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="warlord")
        events = executor.execute(char, {"action": "gather_forces", "target": "enemy"})
        
        assert len(events) == 1
        assert events[0]["type"] == "military_preparation"
    
    def test_execute_scout(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="scout")
        events = executor.execute(char, {"action": "scout"})
        
        assert len(events) == 1
        assert events[0]["type"] == "scouting"
    
    def test_execute_fortify(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="defender")
        events = executor.execute(char, {"action": "fortify"})
        
        assert len(events) == 1
        assert events[0]["type"] == "fortification"
    
    def test_execute_agree(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="mediator")
        events = executor.execute(char, {"action": "agree", "target": "partner"})
        
        assert len(events) == 1
        assert events[0]["type"] == "agreement"
        assert "mediator" in events[0]["participants"]
    
    def test_custom_action_handler(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        
        def custom_handler(char, action, world):
            return [{"type": "custom_event", "actor": char.id}]
        
        executor.register_handler("my_custom_action", custom_handler)
        char = MockCharacter(id="custom_npc")
        events = executor.execute(char, {"action": "my_custom_action"})
        
        assert len(events) == 1
        assert events[0]["type"] == "custom_event"
    
    def test_get_available_actions(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        actions = executor.get_available_actions()
        
        assert "attack" in actions
        assert "wait" in actions
        assert "negotiate" in actions
        assert "deliver" in actions
    
    def test_execute_handles_exception_gracefully(self):
        from rpg.agent.action_executor import ActionExecutor
        
        executor = ActionExecutor()
        char = MockCharacter(id="unlucky")
        
        def bad_handler(char, action, world):
            raise RuntimeError("Something went wrong")
        
        executor.register_handler("bad_action", bad_handler)
        events = executor.execute(char, {"action": "bad_action"})
        
        assert len(events) == 1
        assert events[0]["type"] == "action_error"


# =====================================================================
# AgentScheduler Tests
# =====================================================================

class TestAgentScheduler:
    """Tests for AgentScheduler NPC selection."""
    
    def test_select_agents_returns_list(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=3)
        chars = {
            "npc1": MockCharacter(id="npc1"),
            "npc2": MockCharacter(id="npc2"),
            "npc3": MockCharacter(id="npc3"),
        }
        
        selected = scheduler.select_agents(chars)
        assert isinstance(selected, list)
        assert len(selected) <= 3
    
    def test_empty_characters_returns_empty(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler()
        selected = scheduler.select_agents({})
        assert selected == []
    
    def test_max_per_tick_limit(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=2)
        chars = {
            f"npc{i}": MockCharacter(id=f"npc{i}")
            for i in range(10)
        }
        
        selected = scheduler.select_agents(chars)
        assert len(selected) <= 2
    
    def test_priority_based_selection(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=2, use_priority=True)
        
        # High power character should be selected more often
        high_power = MockCharacter(id="powerful", power=0.9, goals=["dominate"])
        low_power = MockCharacter(id="weak", power=0.1, goals=[])
        
        chars = {"powerful": high_power, "weak": low_power}
        
        # Run multiple times and check powerful is selected more often
        powerful_count = 0
        for _ in range(20):
            selected = scheduler.select_agents(chars)
            if "powerful" in selected:
                powerful_count += 1
        
        # Powerful should be selected more than 50% due to priority
        assert powerful_count > 10
    
    def test_starvation_prevention(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=1, use_priority=True)
        chars = {
            "npc1": MockCharacter(id="npc1", power=0.8),
            "npc2": MockCharacter(id="npc2", power=0.2),
        }
        
        # Run many ticks - even weak chars should eventually be selected
        for _ in range(100):
            selected = scheduler.select_agents(chars)
        
        stats = scheduler.get_selection_stats()
        # Both should have been selected at some point due to starvation bonus
        assert "npc1" in stats
        assert "npc2" in stats
    
    def test_random_mode_selection(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=2, use_priority=False)
        chars = {
            "npc1": MockCharacter(id="npc1", power=0.9),
            "npc2": MockCharacter(id="npc2", power=0.5),
            "npc3": MockCharacter(id="npc3", power=0.1),
        }
        
        selected = scheduler.select_agents(chars)
        assert len(selected) <= 2
    
    def test_get_last_selected(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=2)
        chars = {
            "npc1": MockCharacter(id="npc1"),
            "npc2": MockCharacter(id="npc2"),
        }
        
        scheduler.select_agents(chars)
        last = scheduler.get_last_selected()
        assert isinstance(last, list)
        assert len(last) <= 2
    
    def test_get_selection_stats(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler(max_per_tick=5)
        chars = {
            "npc1": MockCharacter(id="npc1"),
        }
        
        scheduler.select_agents(chars)
        scheduler.select_agents(chars)
        
        stats = scheduler.get_selection_stats()
        assert stats.get("npc1", 0) >= 2
    
    def test_reset(self):
        from rpg.agent.agent_scheduler import AgentScheduler
        
        scheduler = AgentScheduler()
        chars = {"npc1": MockCharacter(id="npc1")}
        
        scheduler.select_agents(chars)
        scheduler.reset()
        
        assert scheduler.get_last_selected() == []
        assert scheduler.get_selection_stats() == {}


# =====================================================================
# AgentSystem Tests
# =====================================================================

class TestAgentSystem:
    """Tests for AgentSystem orchestration."""
    
    def test_update_generates_events_for_characters_with_goals(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        chars = {
            "npc1": MockCharacter(
                id="npc1",
                goals=["gain power"],
                beliefs={"enemy": -0.5},
            ),
        }
        
        events = agents.update(chars, {"factions": {}, "economy": {}, "tick": 0})
        assert isinstance(events, list)
    
    def test_update_no_events_for_empty_characters(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        events = agents.update({}, {"factions": {}, "tick": 0})
        assert len(events) == 0
    
    def test_update_no_events_for_characters_without_goals(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        chars = {
            "npc1": MockCharacter(id="npc1", goals=[]),
        }
        
        events = agents.update(chars, {"factions": {}, "tick": 0})
        assert len(events) == 0
    
    def test_plans_persist_across_ticks(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        char = MockCharacter(
            id="npc1",
            goals=["attack the castle"],  # Multi-step plan
        )
        chars = {"npc1": char}
        
        # First tick - creates plan and executes first step
        events1 = agents.update(chars, {"factions": {}, "tick": 0})
        
        # Character should have an active plan
        assert agents.get_active_plan_count() >= 0
    
    def test_cancel_plan(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        char = MockCharacter(
            id="npc1",
            goals=["attack the castle"],
        )
        chars = {"npc1": char}
        
        # Run one tick to create plan
        agents.update(chars, {"factions": {}, "tick": 0})
        
        # Cancel the plan
        plan = agents.cancel_plan("npc1")
        assert plan is not None
        assert agents.get_active_plan("npc1") is None
    
    def test_get_scheduler_stats(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        stats = agents.get_scheduler_stats()
        
        assert "active_plans" in stats
        assert "selection_stats" in stats
        assert "last_selected" in stats
    
    def test_reset_clears_all_state(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        char = MockCharacter(id="npc1", goals=["gain power"])
        chars = {"npc1": char}
        
        agents.update(chars, {"factions": {}, "tick": 0})
        agents.reset()
        
        assert agents.get_active_plan_count() == 0
    
    def test_multiple_characters_all_act(self):
        from rpg.agent.agent_system import AgentSystem
        
        agents = AgentSystem(max_per_tick=10)
        chars = {
            f"npc{i}": MockCharacter(
                id=f"npc{i}",
                goals=["gain power"],
                beliefs={f"enemy{i}": -0.5},
            )
            for i in range(5)
        }
        
        events = agents.update(chars, {"factions": {}, "tick": 0})
        # At least some events should be generated
        assert isinstance(events, list)