"""Unit tests for RPG GOAP system."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.ai.goap.planner import plan, _goal_satisfied as goal_satisfied
from rpg.ai.goap.actions import Action, default_actions


class TestGoalSatisfied:
    """Test goal satisfaction checking."""

    def test_goal_satisfied_all(self):
        state = {"alive": True, "safe": True}
        goal = {"alive": True}
        assert goal_satisfied(state, goal) is True

    def test_goal_not_satisfied(self):
        state = {"alive": True, "safe": False}
        goal = {"alive": True, "safe": True}
        assert goal_satisfied(state, goal) is False

    def test_goal_satisfied_extra_state(self):
        state = {"alive": True, "safe": True, "extra": True}
        goal = {"alive": True}
        assert goal_satisfied(state, goal) is True

    def test_goal_empty(self):
        state = {"alive": True}
        goal = {}
        assert goal_satisfied(state, goal) is True

    def test_goal_false_value(self):
        state = {"enemy_alive": False}
        goal = {"enemy_alive": False}
        assert goal_satisfied(state, goal) is True

    def test_goal_true_value_not_met(self):
        state = {"enemy_alive": True}
        goal = {"enemy_alive": False}
        assert goal_satisfied(state, goal) is False


class TestAction:
    """Test Action class."""

    def test_create_action(self):
        action = Action("attack", cost=2, preconditions={"enemy_visible": True}, effects={"enemy_alive": False})
        assert action.name == "attack"
        assert action.preconditions == {"enemy_visible": True}
        assert action.effects == {"enemy_alive": False}
        assert action.cost == 2

    def test_is_applicable_true(self):
        action = Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False})
        state = {"enemy_visible": True, "hp": 100}
        assert action.is_applicable(state) is True

    def test_is_applicable_false(self):
        action = Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False})
        state = {"enemy_visible": False, "hp": 100}
        assert action.is_applicable(state) is False

    def test_is_applicable_missing_key(self):
        action = Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False})
        state = {"hp": 100}
        assert action.is_applicable(state) is False

    def test_apply(self):
        action = Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False})
        state = {"enemy_visible": True, "enemy_alive": True}
        new_state = action.apply(state)
        assert new_state["enemy_alive"] is False
        assert new_state["enemy_visible"] is True  # Unchanged

    def test_default_actions(self):
        actions = default_actions()
        assert len(actions) == 5
        names = [a.name for a in actions]
        assert "attack" in names
        assert "flee" in names
        assert "move_to_target" in names
        assert "approach" in names
        assert "idle" in names


class TestPlan:
    """Test GOAP planner."""

    def test_plan_simple(self):
        actions = [
            Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {"enemy_visible": True}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "attack"

    def test_plan_no_applicable_action(self):
        actions = [
            Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {"enemy_visible": False}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result == []  # Returns empty list when no plan found

    def test_plan_multi_step(self):
        actions = [
            Action("move", cost=1, preconditions={}, effects={"enemy_visible": True}),
            Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result is not None
        assert len(result) == 2
        assert result[0].name == "move"
        assert result[1].name == "attack"

    def test_plan_already_satisfied(self):
        actions = [
            Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {"enemy_alive": False}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result == []

    def test_plan_no_solution(self):
        actions = [
            Action("attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {}
        goal = {"impossible": True}
        result = plan(state, goal, actions)
        assert result == []  # Returns empty list when no plan found

    def test_plan_chooses_cheaper(self):
        actions = [
            Action("quick_attack", cost=1, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
            Action("slow_attack", cost=5, preconditions={"enemy_visible": True}, effects={"enemy_alive": False}),
        ]
        state = {"enemy_visible": True}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result is not None
        assert result[0].name == "quick_attack"

    def test_plan_three_step(self):
        actions = [
            Action("find_enemy", cost=1, preconditions={}, effects={"has_target": True}),
            Action("approach", cost=1, preconditions={"has_target": True}, effects={"in_range": True}),
            Action("attack", cost=1, preconditions={"in_range": True}, effects={"enemy_alive": False}),
        ]
        state = {}
        goal = {"enemy_alive": False}
        result = plan(state, goal, actions)
        assert result is not None
        assert len(result) == 3
        assert result[0].name == "find_enemy"
        assert result[1].name == "approach"
        assert result[2].name == "attack"