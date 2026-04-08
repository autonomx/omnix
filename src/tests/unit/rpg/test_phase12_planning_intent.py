"""Phase 12 — Planning / Intent system tests.

Tests covering sub-phases 12.0 – 12.8.
"""
from __future__ import annotations

import copy
import os
import sys
import types

_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
for _mod_name, _rel_path in [
    ("app", "app"),
    ("app.rpg", os.path.join("app", "rpg")),
    ("app.rpg.planning", os.path.join("app", "rpg", "planning")),
]:
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.__path__ = [os.path.join(_SRC_DIR, _rel_path)]
        sys.modules[_mod_name] = _m

from app.rpg.planning.intent_system import (
    MAX_ACTIVE_GOALS,
    MAX_COMPLETED_GOALS,
    MAX_GLOBAL_OBJECTIVES,
    MAX_PLAN_STEPS,
    CompanionPlanner,
    FactionIntentCoordinator,
    GoalGenerator,
    GoalState,
    IntentState,
    Plan,
    PlanBuilder,
    PlanExecutor,
    PlanInterruptHandler,
    PlannerInspector,
    PlanningDeterminismValidator,
    PlanningSystemState,
    PlanStep,
    _clamp,
    _safe_float,
    _safe_int,
    _safe_str,
)

# ── 12.0 State foundations ──────────────────────────────────────────────

class TestGoalState:
    def test_default(self):
        g = GoalState()
        assert g.status == "active"
        assert g.priority == 0.5

    def test_round_trip(self):
        g = GoalState(goal_id="g1", actor_id="a1", goal_type="survive",
                      priority=0.8, progress=0.3)
        d = g.to_dict()
        g2 = GoalState.from_dict(d)
        assert g2.to_dict() == d

    def test_priority_clamped(self):
        g = GoalState.from_dict({"priority": 5.0})
        assert g.priority <= 1.0

    def test_progress_clamped(self):
        g = GoalState.from_dict({"progress": -1.0})
        assert g.progress >= 0.0

    def test_from_dict_missing(self):
        g = GoalState.from_dict({})
        assert g.goal_id == ""
        assert g.status == "active"


class TestPlanStep:
    def test_default(self):
        s = PlanStep()
        assert s.status == "pending"

    def test_round_trip(self):
        s = PlanStep(step_id="s1", action_type="attack", target_id="t1")
        d = s.to_dict()
        s2 = PlanStep.from_dict(d)
        assert s2.to_dict() == d

    def test_from_dict_missing(self):
        s = PlanStep.from_dict({})
        assert s.step_id == ""


class TestPlan:
    def test_default(self):
        p = Plan()
        assert p.status == "active"
        assert p.steps == []

    def test_round_trip(self):
        p = Plan(plan_id="p1", goal_id="g1",
                 steps=[PlanStep(step_id="s1", action_type="move")])
        d = p.to_dict()
        p2 = Plan.from_dict(d)
        assert p2.to_dict() == d

    def test_from_dict_empty_steps(self):
        p = Plan.from_dict({"steps": None})
        assert p.steps == []


class TestIntentState:
    def test_default(self):
        i = IntentState()
        assert i.active_goals == []

    def test_round_trip(self):
        i = IntentState(actor_id="a1",
                        active_goals=[GoalState(goal_id="g1")])
        d = i.to_dict()
        i2 = IntentState.from_dict(d)
        assert i2.to_dict() == d

    def test_enforce_bounds(self):
        i = IntentState(active_goals=[GoalState(priority=float(x)/10)
                                      for x in range(10)])
        i._enforce_bounds()
        assert len(i.active_goals) <= MAX_ACTIVE_GOALS

    def test_completed_bounds(self):
        i = IntentState(completed_goals=[GoalState() for _ in range(25)])
        i._enforce_bounds()
        assert len(i.completed_goals) <= MAX_COMPLETED_GOALS


class TestPlanningSystemState:
    def test_default(self):
        s = PlanningSystemState()
        assert s.actors == {}
        assert s.tick == 0

    def test_round_trip(self):
        s = PlanningSystemState(
            actors={"a1": IntentState(actor_id="a1")},
            global_objectives=[{"obj": "win"}],
            tick=5,
        )
        d = s.to_dict()
        s2 = PlanningSystemState.from_dict(d)
        assert s2.to_dict() == d


# ── 12.1 Goal generation ────────────────────────────────────────────────

class TestGoalGenerator:
    def test_hostile_target_goal(self):
        goals = GoalGenerator.generate_goals(
            "npc1", {"hostile_targets": ["player"]}, {}, {}, tick=1
        )
        assert any(g.goal_type == "neutralize" for g in goals)

    def test_trusted_ally_goal(self):
        goals = GoalGenerator.generate_goals(
            "npc1", {"trusted_allies": ["friend"]}, {}, {}, tick=1
        )
        assert any(g.goal_type == "protect" for g in goals)

    def test_high_threat_goal(self):
        goals = GoalGenerator.generate_goals(
            "npc1", {"world_threat_level": 0.8}, {}, {}, tick=1
        )
        assert any(g.goal_type == "survive" for g in goals)

    def test_low_resources_goal(self):
        goals = GoalGenerator.generate_goals(
            "npc1", {}, {}, {"resources": 0.1}, tick=1
        )
        assert any(g.goal_type == "acquire" for g in goals)

    def test_max_three_goals(self):
        goals = GoalGenerator.generate_goals(
            "npc1",
            {"hostile_targets": ["x"], "trusted_allies": ["y"], "world_threat_level": 0.9},
            {}, {"resources": 0.1}, tick=1,
        )
        assert len(goals) <= 3

    def test_no_goals_when_peaceful(self):
        goals = GoalGenerator.generate_goals("npc1", {}, {}, {}, tick=1)
        assert len(goals) == 0

    def test_goals_sorted_by_priority(self):
        goals = GoalGenerator.generate_goals(
            "npc1",
            {"hostile_targets": ["x"], "world_threat_level": 0.9},
            {}, {}, tick=1,
        )
        if len(goals) >= 2:
            assert goals[0].priority >= goals[1].priority

    def test_goal_actor_id(self):
        goals = GoalGenerator.generate_goals(
            "npc99", {"hostile_targets": ["x"]}, {}, {}, tick=1
        )
        assert all(g.actor_id == "npc99" for g in goals)


# ── 12.2 Plan building ──────────────────────────────────────────────────

class TestPlanBuilder:
    def test_neutralize_plan(self):
        goal = GoalState(goal_id="g1", goal_type="neutralize",
                         metadata={"targets": ["enemy1"]})
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert len(plan.steps) == 3
        assert plan.steps[0].action_type == "approach"

    def test_protect_plan(self):
        goal = GoalState(goal_id="g2", goal_type="protect",
                         metadata={"allies": ["friend1"]})
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert plan.steps[0].action_type == "move_to"

    def test_survive_plan(self):
        goal = GoalState(goal_id="g3", goal_type="survive")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert plan.steps[0].action_type == "assess"

    def test_acquire_plan(self):
        goal = GoalState(goal_id="g4", goal_type="acquire")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert plan.steps[0].action_type == "locate"

    def test_unknown_type_fallback(self):
        goal = GoalState(goal_id="g5", goal_type="unknown")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert len(plan.steps) == 3  # fallback template

    def test_max_steps(self):
        goal = GoalState(goal_id="g6", goal_type="neutralize")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert len(plan.steps) <= MAX_PLAN_STEPS

    def test_plan_has_goal_id(self):
        goal = GoalState(goal_id="g7", goal_type="neutralize")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert plan.goal_id == "g7"

    def test_steps_start_pending(self):
        goal = GoalState(goal_id="g8", goal_type="protect")
        plan = PlanBuilder.build_plan(goal, {}, {})
        assert all(s.status == "pending" for s in plan.steps)


# ── 12.3 Plan execution ─────────────────────────────────────────────────

class TestPlanExecutor:
    def _make_plan(self):
        return Plan(
            plan_id="p1", goal_id="g1",
            steps=[
                PlanStep(step_id="s1", action_type="approach", status="pending"),
                PlanStep(step_id="s2", action_type="engage", status="pending"),
            ],
        )

    def test_get_current_step(self):
        plan = self._make_plan()
        step = PlanExecutor.get_current_step(plan)
        assert step is not None
        assert step.step_id == "s1"

    def test_get_current_step_none(self):
        plan = Plan(steps=[PlanStep(status="completed")])
        assert PlanExecutor.get_current_step(plan) is None

    def test_advance_step_success(self):
        plan = self._make_plan()
        PlanExecutor.advance_step(plan, "success")
        assert plan.steps[0].status == "completed"
        assert plan.steps[1].status == "pending"

    def test_advance_step_failure(self):
        plan = self._make_plan()
        PlanExecutor.advance_step(plan, "failure")
        assert plan.steps[0].status == "failed"

    def test_plan_completed_after_all_steps(self):
        plan = self._make_plan()
        PlanExecutor.advance_step(plan, "success")
        PlanExecutor.advance_step(plan, "success")
        assert PlanExecutor.is_plan_complete(plan)
        assert plan.status == "completed"

    def test_plan_failed_after_failure(self):
        plan = self._make_plan()
        PlanExecutor.advance_step(plan, "success")
        PlanExecutor.advance_step(plan, "failure")
        assert plan.status == "failed"

    def test_get_plan_action(self):
        plan = self._make_plan()
        action = PlanExecutor.get_plan_action(plan, {})
        assert action["action"] == "approach"

    def test_get_plan_action_no_steps(self):
        plan = Plan(steps=[PlanStep(status="completed")])
        action = PlanExecutor.get_plan_action(plan, {})
        assert action["action"] == "wait"


# ── 12.4 Plan interruption ──────────────────────────────────────────────

class TestPlanInterruptHandler:
    def _make_plan(self):
        return Plan(plan_id="p1", goal_id="g1",
                    steps=[PlanStep(status="pending")])

    def test_no_interrupts(self):
        plan = self._make_plan()
        reasons = PlanInterruptHandler.check_interrupts(plan, [], {})
        assert reasons == []

    def test_threat_detected(self):
        plan = self._make_plan()
        reasons = PlanInterruptHandler.check_interrupts(
            plan, [{"type": "attack"}], {}
        )
        assert "threat_detected" in reasons

    def test_goal_invalidated(self):
        plan = self._make_plan()
        reasons = PlanInterruptHandler.check_interrupts(
            plan, [{"type": "goal_completed", "goal_id": "g1"}], {}
        )
        assert "goal_invalidated" in reasons

    def test_ally_in_danger(self):
        plan = self._make_plan()
        reasons = PlanInterruptHandler.check_interrupts(
            plan, [{"type": "ally_attacked"}], {}
        )
        assert "ally_in_danger" in reasons

    def test_should_replan_critical(self):
        assert PlanInterruptHandler.should_replan(
            self._make_plan(), ["threat_detected"]
        )

    def test_should_not_replan_noncritical(self):
        assert not PlanInterruptHandler.should_replan(
            self._make_plan(), ["better_opportunity"]
        )

    def test_should_not_replan_empty(self):
        assert not PlanInterruptHandler.should_replan(self._make_plan(), [])

    def test_suspend_plan(self):
        plan = self._make_plan()
        PlanInterruptHandler.suspend_plan(plan)
        assert plan.status == "suspended"

    def test_resume_plan(self):
        plan = self._make_plan()
        plan.status = "suspended"
        PlanInterruptHandler.resume_plan(plan)
        assert plan.status == "active"

    def test_resume_non_suspended(self):
        plan = self._make_plan()
        plan.status = "completed"
        PlanInterruptHandler.resume_plan(plan)
        assert plan.status == "completed"


# ── 12.5 Companion planning ─────────────────────────────────────────────

class TestCompanionPlanner:
    def test_attack_companion(self):
        leader_plan = Plan(
            plan_id="lp1", goal_id="g1",
            steps=[PlanStep(action_type="approach"), PlanStep(action_type="engage")],
        )
        comp = CompanionPlanner.generate_companion_plan(
            "comp1", "leader", leader_plan, {}
        )
        assert comp.steps[0].action_type == "support_attack"

    def test_protect_companion(self):
        leader_plan = Plan(
            plan_id="lp2", goal_id="g2",
            steps=[PlanStep(action_type="move_to"), PlanStep(action_type="guard")],
        )
        comp = CompanionPlanner.generate_companion_plan(
            "comp1", "leader", leader_plan, {}
        )
        assert comp.steps[0].action_type == "cover_ally"

    def test_companion_follows(self):
        leader_plan = Plan(
            plan_id="lp3", goal_id="g3",
            steps=[PlanStep(action_type="assess")],
        )
        comp = CompanionPlanner.generate_companion_plan(
            "comp1", "leader", leader_plan, {}
        )
        assert comp.steps[-1].action_type == "follow"

    def test_companion_plan_has_goal_id(self):
        leader_plan = Plan(plan_id="lp4", goal_id="g4",
                           steps=[PlanStep(action_type="engage")])
        comp = CompanionPlanner.generate_companion_plan(
            "comp1", "leader", leader_plan, {}
        )
        assert comp.goal_id == "g4"


# ── 12.6 Faction coordination ───────────────────────────────────────────

class TestFactionIntentCoordinator:
    def test_no_conflict(self):
        plans = {
            "a1": Plan(steps=[PlanStep(target_id="t1", status="pending")]),
            "a2": Plan(steps=[PlanStep(target_id="t2", status="pending")]),
        }
        result = FactionIntentCoordinator.coordinate_faction_plans("f1", plans, [])
        assert result["conflicts_resolved"] == 0

    def test_conflict_resolved(self):
        plans = {
            "a1": Plan(steps=[PlanStep(target_id="t1", status="pending")]),
            "a2": Plan(steps=[PlanStep(target_id="t1", status="pending")]),
        }
        result = FactionIntentCoordinator.coordinate_faction_plans("f1", plans, [])
        assert result["conflicts_resolved"] == 1
        roles = {v["role"] for v in result["assignments"].values()}
        assert "primary" in roles
        assert "flank" in roles

    def test_empty_plans(self):
        result = FactionIntentCoordinator.coordinate_faction_plans("f1", {}, [])
        assert result["conflicts_resolved"] == 0

    def test_completed_steps_ignored(self):
        plans = {
            "a1": Plan(steps=[PlanStep(target_id="t1", status="completed")]),
        }
        result = FactionIntentCoordinator.coordinate_faction_plans("f1", plans, [])
        assert len(result["assignments"]) == 0


# ── 12.7 Planner inspector ──────────────────────────────────────────────

class TestPlannerInspector:
    def test_inspect_actor_plans(self):
        intent = IntentState(actor_id="a1",
                             active_goals=[GoalState(goal_id="g1")])
        info = PlannerInspector.inspect_actor_plans(intent)
        assert info["actor_id"] == "a1"
        assert info["active_goal_count"] == 1

    def test_inspect_plan_timeline(self):
        plan = Plan(steps=[
            PlanStep(step_id="s1", action_type="move", status="completed"),
            PlanStep(step_id="s2", action_type="engage", status="pending"),
        ])
        tl = PlannerInspector.inspect_plan_timeline(plan)
        assert len(tl) == 2
        assert tl[0]["status"] == "completed"

    def test_get_planning_statistics(self):
        state = PlanningSystemState(
            actors={"a1": IntentState(
                active_goals=[GoalState()],
                completed_goals=[GoalState(), GoalState()],
            )},
            global_objectives=[{"obj": "win"}],
            tick=10,
        )
        stats = PlannerInspector.get_planning_statistics(state)
        assert stats["actor_count"] == 1
        assert stats["total_active_goals"] == 1
        assert stats["total_completed_goals"] == 2
        assert stats["tick"] == 10


# ── 12.8 Determinism validation ─────────────────────────────────────────

class TestPlanningDeterminismValidator:
    def test_validate_determinism_equal(self):
        s1 = PlanningSystemState(tick=1)
        s2 = PlanningSystemState(tick=1)
        assert PlanningDeterminismValidator.validate_determinism(s1, s2)

    def test_validate_determinism_unequal(self):
        s1 = PlanningSystemState(tick=1)
        s2 = PlanningSystemState(tick=2)
        assert not PlanningDeterminismValidator.validate_determinism(s1, s2)

    def test_validate_bounds_ok(self):
        s = PlanningSystemState()
        assert PlanningDeterminismValidator.validate_bounds(s) == []

    def test_validate_bounds_goals_exceeded(self):
        s = PlanningSystemState(actors={
            "a1": IntentState(active_goals=[GoalState() for _ in range(10)])
        })
        violations = PlanningDeterminismValidator.validate_bounds(s)
        assert any("active_goals" in v for v in violations)

    def test_validate_bounds_priority_out_of_range(self):
        s = PlanningSystemState(actors={
            "a1": IntentState(active_goals=[GoalState(priority=5.0)])
        })
        violations = PlanningDeterminismValidator.validate_bounds(s)
        assert any("priority" in v for v in violations)

    def test_validate_bounds_objectives_exceeded(self):
        s = PlanningSystemState(global_objectives=[{} for _ in range(15)])
        violations = PlanningDeterminismValidator.validate_bounds(s)
        assert any("global_objectives" in v for v in violations)

    def test_normalize_trims_goals(self):
        s = PlanningSystemState(actors={
            "a1": IntentState(active_goals=[
                GoalState(priority=float(i)/10) for i in range(10)
            ])
        })
        norm = PlanningDeterminismValidator.normalize_state(s)
        assert len(norm.actors["a1"].active_goals) <= MAX_ACTIVE_GOALS

    def test_normalize_clamps_priority(self):
        s = PlanningSystemState(actors={
            "a1": IntentState(active_goals=[GoalState(priority=5.0)])
        })
        norm = PlanningDeterminismValidator.normalize_state(s)
        assert norm.actors["a1"].active_goals[0].priority <= 1.0

    def test_normalize_trims_objectives(self):
        s = PlanningSystemState(global_objectives=[{} for _ in range(15)])
        norm = PlanningDeterminismValidator.normalize_state(s)
        assert len(norm.global_objectives) <= MAX_GLOBAL_OBJECTIVES

    def test_normalized_passes_bounds(self):
        s = PlanningSystemState(
            actors={"a1": IntentState(
                active_goals=[GoalState(priority=5.0) for _ in range(10)],
                completed_goals=[GoalState() for _ in range(25)],
            )},
            global_objectives=[{} for _ in range(15)],
        )
        norm = PlanningDeterminismValidator.normalize_state(s)
        assert PlanningDeterminismValidator.validate_bounds(norm) == []


# ── Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:
    def test_goal_generation_deterministic(self):
        # Reset counter for determinism
        GoalGenerator._counter = 0
        g1 = GoalGenerator.generate_goals(
            "npc1", {"hostile_targets": ["x"]}, {}, {}, tick=1
        )
        GoalGenerator._counter = 0
        g2 = GoalGenerator.generate_goals(
            "npc1", {"hostile_targets": ["x"]}, {}, {}, tick=1
        )
        assert [g.to_dict() for g in g1] == [g.to_dict() for g in g2]

    def test_plan_build_deterministic(self):
        PlanBuilder._counter = 0
        g = GoalState(goal_id="g1", goal_type="neutralize",
                      metadata={"targets": ["e1"]})
        p1 = PlanBuilder.build_plan(g, {}, {})
        PlanBuilder._counter = 0
        p2 = PlanBuilder.build_plan(g, {}, {})
        assert p1.to_dict() == p2.to_dict()

    def test_execution_deterministic(self):
        def run():
            p = Plan(steps=[
                PlanStep(step_id="s1", status="pending"),
                PlanStep(step_id="s2", status="pending"),
            ])
            PlanExecutor.advance_step(p, "success")
            return p.to_dict()
        assert run() == run()

    def test_system_state_round_trip(self):
        s = PlanningSystemState(
            actors={"a1": IntentState(
                actor_id="a1",
                active_goals=[GoalState(goal_id="g1", priority=0.8)],
            )},
            tick=5,
        )
        d = s.to_dict()
        s2 = PlanningSystemState.from_dict(d)
        assert s2.to_dict() == d


# ── Helpers ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_clamp(self):
        assert _clamp(1.5) == 1.0
        assert _clamp(-0.5) == 0.0

    def test_safe_str(self):
        assert _safe_str(None) == ""

    def test_safe_float(self):
        assert _safe_float("bad") == 0.0
        assert _safe_float("0.5") == 0.5

    def test_safe_int(self):
        assert _safe_int("bad") == 0
        assert _safe_int("5") == 5
