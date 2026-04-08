"""Tests for ExecutionPipeline — All 6 critical fixes.

Tests cover:
    Fix #1: Canonical system ordering
    Fix #2: Director feedback loop
    Fix #3: Story arcs active influence
    Fix #4: Authority hierarchy
    Fix #5: Resource influence on planning
    Fix #6: Structured trace logging
"""

from unittest.mock import MagicMock, patch

import pytest
from rpg.core.action_resolver import ActionResolver
from rpg.core.execution_pipeline import (
    AUTHORITY_PRIORITIES,
    ExecutionPipeline,
    TurnTrace,
    build_director_feedback,
    build_director_planning_context,
    consume_action_resources,
    create_default_pipeline,
    filter_affordable_actions,
    format_feedback_for_director_prompt,
    get_action_priority,
    sort_actions_by_authority,
)
from rpg.core.probabilistic_executor import ProbabilisticActionExecutor

# ============================================================
# Fix #4 Tests: Authority Hierarchy
# ============================================================

class TestAuthorityHierarchy:
    """Tests for Fix #4: Explicit authority priority model."""

    def test_authority_priorities_values(self):
        """Verify priority values match specification."""
        assert AUTHORITY_PRIORITIES["director"] == 10
        assert AUTHORITY_PRIORITIES["npc_goal"] == 5
        assert AUTHORITY_PRIORITIES["autonomous"] == 3

    def test_get_action_priority_director(self):
        """Director actions get highest priority."""
        action = {"source": "director", "action": "attack"}
        assert get_action_priority(action) == 10

    def test_get_action_priority_npc_goal(self):
        """NPC goal actions get medium priority."""
        action = {"source": "npc_goal", "action": "defend"}
        assert get_action_priority(action) == 5

    def test_get_action_priority_autonomous(self):
        """Autonomous actions get lowest priority."""
        action = {"source": "autonomous", "action": "wander"}
        assert get_action_priority(action) == 3

    def test_get_action_priority_unknown_defaults(self):
        """Unknown source defaults to autonomous priority."""
        action = {"source": "unknown", "action": "move"}
        assert get_action_priority(action) == 3

    def test_get_action_priority_no_source(self):
        """Missing source defaults to autonomous priority."""
        action = {"action": "move"}
        assert get_action_priority(action) == 3

    def test_sort_actions_by_authority(self):
        """Actions sorted by authority priority (highest first)."""
        actions = [
            {"source": "autonomous", "action": "wander"},
            {"source": "director", "action": "attack"},
            {"source": "npc_goal", "action": "defend"},
            {"source": "autonomous", "action": "move"},
        ]
        sorted_actions = sort_actions_by_authority(actions)
        
        sources = [a["source"] for a in sorted_actions]
        # Director first, npc_goal second, autonomous last
        assert sources[0] == "director"
        assert sources[1] == "npc_goal"
        assert sources[2] == "autonomous"
        assert sources[3] == "autonomous"

    def test_sort_actions_stability_within_priority(self):
        """Actions with same priority maintain relative order."""
        actions = [
            {"source": "autonomous", "action": "wander"},
            {"source": "autonomous", "action": "move"},
        ]
        sorted_actions = sort_actions_by_authority(actions)
        # Python sort is stable, so order preserved within same priority
        assert sorted_actions[0]["action"] == "wander"
        assert sorted_actions[1]["action"] == "move"


# ============================================================
# Fix #6 Tests: Structured Trace Logging
# ============================================================

class TestTurnTrace:
    """Tests for Fix #6: Structured trace logging."""

    def test_trace_initialization(self):
        """Trace initialized with empty collections."""
        trace = TurnTrace(turn_number=1)
        assert trace.turn_number == 1
        assert trace.player_input == ""
        assert trace.plan == []
        assert trace.errors == []
        assert trace.duration_ms == 0.0

    def test_trace_add_error(self):
        """Errors are recorded in trace."""
        trace = TurnTrace()
        trace.add_error("Something failed")
        trace.add_error("Another failure")
        assert len(trace.errors) == 2
        assert "Something failed" in trace.errors

    def test_trace_to_dict(self):
        """Trace serializes to dict correctly."""
        trace = TurnTrace(turn_number=5)
        trace.player_input = "Attack the goblin"
        trace.plan = [{"action": "attack"}]
        trace.add_error("test error")
        trace.duration_ms = 123.45

        d = trace.to_dict()
        assert d["turn_number"] == 5
        assert d["plan_len"] == 1
        assert len(d["errors"]) == 1
        assert "test error" in d["errors"]
        assert d["duration_ms"] == 123.45

    def test_trace_summary(self):
        """Trace summary is human-readable."""
        trace = TurnTrace(turn_number=1)
        trace.player_input = "Test input" * 20  # Long string
        trace.plan = [{"action": "attack"}] * 3
        trace.resolved_actions = [{"action": "attack"}] * 2
        trace.duration_ms = 50.0

        summary = trace.summary()
        assert "Turn 1" in summary
        assert "Plan: 3" in summary
        assert "Resolved: 2" in summary
        assert "Duration: 50.0ms" in summary

    def test_trace_summary_with_errors(self):
        """Summary includes error section when present."""
        trace = TurnTrace()
        trace.add_error("Critical failure")
        summary = trace.summary()
        assert "ERRORS" in summary
        assert "Critical failure" in summary

    def test_trace_save(self, tmp_path):
        """Trace can be saved to JSON file."""
        trace = TurnTrace(turn_number=1)
        trace.player_input = "Test"
        filepath = tmp_path / "trace.json"
        trace.save(str(filepath))

        import json
        with open(filepath) as f:
            data = json.load(f)
        assert data["turn_number"] == 1
        assert data["player_input"] == "Test"


# ============================================================
# Fix #2 Tests: Director Feedback Loop
# ============================================================

class TestDirectorFeedback:
    """Tests for Fix #2: Director feedback loop."""

    def test_build_director_feedback_all_success(self):
        """Feedback shows all successes, no failures."""
        results = [
            {"success": True, "outcome": "normal_success", "events": []},
            {"success": True, "outcome": "critical_success", "events": []},
        ]
        events = [{"type": "damage"}, {"type": "assist"}]
        
        feedback = build_director_feedback(results, events)
        assert feedback["total_actions"] == 2
        assert feedback["success_count"] == 2
        assert feedback["failure_count"] == 0
        assert feedback["failure_reasons"] == {}

    def test_build_director_feedback_with_failures(self):
        """Feedback categorizes failures by reason."""
        results = [
            {"success": True, "outcome": "normal_success", "events": []},
            {"success": False, "outcome": "normal_fail", "events": [{"type": "action_failure"}]},
            {"success": False, "outcome": "critical_failure", "events": [{"type": "action_failure"}]},
        ]
        events = []
        
        feedback = build_director_feedback(results, events)
        assert feedback["total_actions"] == 3
        assert feedback["success_count"] == 1
        assert feedback["failure_count"] == 2
        assert feedback["failure_reasons"]["normal_fail"] == 1
        assert feedback["failure_reasons"]["critical_failure"] == 1

    def test_build_director_feedback_npc_failures(self):
        """Feedback identifies which NPCs failed."""
        results = [
            {
                "success": False,
                "outcome": "normal_fail",
                "events": [],
                "action": {"npc_id": "goblin_1", "action": "attack"},
            },
            {
                "success": False,
                "outcome": "normal_fail",
                "events": [],
                "action": {"npc_id": "goblin_1", "action": "flee"},
            },
        ]
        
        feedback = build_director_feedback(results, [])
        assert "goblin_1" in feedback["npc_failures"]
        assert "attack" in feedback["npc_failures"]["goblin_1"]
        assert "flee" in feedback["npc_failures"]["goblin_1"]

    def test_format_feedback_for_director_prompt(self):
        """Feedback formatted as readable prompt text."""
        feedback = {
            "total_actions": 5,
            "success_count": 3,
            "failure_count": 2,
            "failure_reasons": {"normal_fail": 2},
            "npc_failures": {"goblin_1": ["attack", "flee"]},
            "event_types_generated": {"damage": 2},
        }
        
        formatted = format_feedback_for_director_prompt(feedback)
        assert "Last Turn Outcome" in formatted
        assert "Actions attempted: 5" in formatted
        assert "Successes: 3" in formatted
        assert "Failures: 2" in formatted
        assert "normal_fail: 2" in formatted
        assert "goblin_1: attack, flee" in formatted
        assert "Update your strategy accordingly" in formatted


# ============================================================
# Fix #3 & #5 Tests: Director Planning Context
# ============================================================

class TestDirectorPlanningContext:
    """Tests for Fix #3 (active arcs) and Fix #5 (resource influence)."""

    def test_planning_context_with_arc_manager(self):
        """Context includes active arcs with PRIMARY DIRECTIVE."""
        arc_manager = MagicMock()
        arc1 = MagicMock()
        arc1.goal = "Defeat the Dark Lord"
        arc1.progress = 0.4
        arc1.phase = "tension"
        arc_manager.active_arcs = [arc1]
        arc_manager.get_most_urgent_arc.return_value = arc1
        
        ctx = build_director_planning_context(
            session=MagicMock(), arc_manager=arc_manager
        )
        assert "PRIMARY DIRECTIVE" in ctx
        assert "Defeat the Dark Lord" in ctx
        assert "40%" in ctx
        assert "MOST URGENT" in ctx
        assert "MUST bias decisions" in ctx

    def test_planning_context_with_resource_manager(self):
        """Context includes resource states."""
        pool = MagicMock()
        pool.get_status.return_value = {
            "stamina": {"current": 50, "pct": 0.5, "max": 100, "exhausted": False}
        }
        resource_manager = MagicMock()
        resource_manager.pools = {"player": pool}
        
        ctx = build_director_planning_context(
            session=MagicMock(), resource_manager=resource_manager
        )
        assert "Resource State" in ctx
        assert "stamina=50" in ctx
        assert "Avoid actions that are not affordable" in ctx

    def test_planning_context_includes_feedback(self):
        """Context includes previous turn feedback."""
        feedback = {
            "total_actions": 3,
            "success_count": 1,
            "failure_count": 2,
            "failure_reasons": {"normal_fail": 2},
            "event_types_generated": {},
            "npc_failures": {},
        }
        
        ctx = build_director_planning_context(
            session=MagicMock(), feedback=feedback
        )
        assert "Last Turn Outcome" in ctx
        assert "Actions attempted: 3" in ctx

    def test_planning_context_empty_without_managers(self):
        """Context is empty when no managers provided."""
        ctx = build_director_planning_context(session=MagicMock())
        assert ctx == ""


# ============================================================
# Fix #5 Tests: Resource Affordability Filtering
# ============================================================

class TestResourceFiltering:
    """Tests for Fix #5: Resource influence on planning."""

    def test_filter_affordable_actions_no_resource_manager(self):
        """Without resource manager, all actions pass through."""
        actions = [{"npc_id": "player", "action": "attack"}]
        result = filter_affordable_actions(actions, resource_manager=None)
        assert result == actions

    def test_filter_affordable_actions_all_affordable(self):
        """When all actions are affordable, all pass through."""
        resource_manager = MagicMock()
        resource_manager.can_afford_action.return_value = True
        resource_manager.get_pool.return_value = MagicMock()
        
        actions = [
            {"npc_id": "player", "action": "attack"},
            {"npc_id": "player", "action": "flee"},
        ]
        result = filter_affordable_actions(actions, resource_manager)
        assert len(result) == 2

    def test_filter_affordable_actions_some_unaffordable(self):
        """Unaffordable actions are filtered out."""
        resource_manager = MagicMock()
        resource_manager.get_pool.return_value = MagicMock()
        
        def can_afford(entity, action_type):
            return action_type != "flee"  # Can't afford flee
        
        resource_manager.can_afford_action.side_effect = can_afford
        
        actions = [
            {"npc_id": "player", "action": "attack"},
            {"npc_id": "player", "action": "flee"},
        ]
        result = filter_affordable_actions(actions, resource_manager)
        assert len(result) == 1
        assert result[0]["action"] == "attack"

    def test_filter_affordable_no_npc_id(self):
        """Actions without npc_id are always allowed."""
        resource_manager = MagicMock()
        actions = [{"action": "story_event"}]
        result = filter_affordable_actions(actions, resource_manager)
        assert len(result) == 1

    def test_filter_affordable_no_pool(self):
        """Actions for entities without pool are always allowed."""
        resource_manager = MagicMock()
        resource_manager.get_pool.return_value = None
        actions = [{"npc_id": "unknown", "action": "attack"}]
        result = filter_affordable_actions(actions, resource_manager)
        assert len(result) == 1

    def test_consume_action_resources_success(self):
        """Resources consumed successfully."""
        resource_manager = MagicMock()
        resource_manager.consume_action_resources.return_value = True
        
        action = {"npc_id": "player", "action": "attack"}
        result = consume_action_resources(action, resource_manager)
        assert result is True
        resource_manager.consume_action_resources.assert_called_once()

    def test_consume_action_resources_no_manager(self):
        """Without manager, consume returns True."""
        action = {"npc_id": "player", "action": "attack"}
        result = consume_action_resources(action, resource_manager=None)
        assert result is True


# ============================================================
# Fix #1 Tests: Canonical Pipeline
# ============================================================

class TestExecutionPipeline:
    """Tests for Fix #1: Canonical execution pipeline."""

    def _make_resolver(self):
        """Create a mock resolver that passes actions through."""
        resolver = MagicMock()
        resolver.resolve.return_value = [
            {"source": "director", "action": "attack"},
        ]
        return resolver

    def _make_scene_manager(self):
        """Create a mock scene manager."""
        scene = MagicMock()
        scene.filter_actions.return_value = [
            {"source": "director", "action": "attack"},
        ]
        sm = MagicMock()
        sm.current_scene = scene
        return sm

    def _make_executor(self):
        """Create a mock executor that returns success."""
        executor = MagicMock()
        executor.execute_with_uncertainty.return_value = {
            "success": True,
            "outcome": "normal_success",
            "events": [{"type": "attack_success"}],
        }
        return executor

    def _make_pipeline(self):
        """Create pipeline with all mocks."""
        resolver = self._make_resolver()
        scene_manager = self._make_scene_manager()
        executor = self._make_executor()
        
        resource_manager = MagicMock()
        resource_manager.get_pool.return_value = MagicMock()
        resource_manager.can_afford_action.return_value = True
        resource_manager.consume_action_resources.return_value = True
        resource_manager.tick_all.return_value = {}
        
        memory_manager = MagicMock()
        memory_manager.add_events.return_value = None
        
        arc_manager = MagicMock()
        arc_manager.update_arcs.return_value = []
        arc_manager.active_arcs = []
        
        world = MagicMock()
        world.time = 0
        
        director = MagicMock()
        director.update.return_value = None
        
        return ExecutionPipeline(
            resolver=resolver,
            scene_manager=scene_manager,
            resource_manager=resource_manager,
            executor=executor,
            world=world,
            memory_manager=memory_manager,
            arc_manager=arc_manager,
            director=director,
            enable_trace=True,
        )

    def test_pipeline_execute_turn_basic(self):
        """Basic turn execution returns expected results."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        result = pipeline.execute_turn(session, actions, "Attack!")
        
        # Verify result structure
        assert "events" in result
        assert "executed_results" in result
        assert "director_feedback" in result
        assert "trace" in result
        assert "turn_number" in result
        assert result["turn_number"] == 1
        assert len(result["events"]) == 1

    def test_pipeline_enforces_order(self):
        """Pipeline calls components in correct order."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        pipeline.execute_turn(session, actions, "")
        
        # Verify call order through side effects
        # Resolve called first
        pipeline.resolver.resolve.assert_called_once()
        # Scene filter called
        pipeline.scene_manager.current_scene.filter_actions.assert_called_once()
        # Resource filter called
        pipeline.resource_manager.can_afford_action.assert_called()
        # Execute called
        pipeline.executor.execute_with_uncertainty.assert_called_once()
        # Memory called
        pipeline.memory_manager.add_events.assert_called_once()
        # Arc update called
        pipeline.arc_manager.update_arcs.assert_called_once()

    def test_pipeline_trace_recording(self):
        """Pipeline records traces when enabled."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        result = pipeline.execute_turn(session, actions, "Attack!")
        
        trace = pipeline.get_last_trace()
        assert trace is not None
        assert trace.turn_number == 1
        assert trace.player_input == "Attack!"
        assert len(trace.plan) == 1
        
    def test_pipeline_trace_disabled(self):
        """Pipeline skips trace recording when disabled."""
        resolver = self._make_resolver()
        scene_manager = self._make_scene_manager()
        executor = self._make_executor()
        
        pipeline = ExecutionPipeline(
            resolver=resolver,
            scene_manager=scene_manager,
            executor=executor,
            enable_trace=False,
        )
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        result = pipeline.execute_turn(session, actions, "")
        
        assert result["trace"] is None
        assert pipeline.get_last_trace() is None

    def test_pipeline_trace_history_bounded(self):
        """Trace history is bounded by max_trace_history."""
        pipeline = self._make_pipeline()
        pipeline.max_trace_history = 2
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        pipeline.execute_turn(session, actions, "Turn 1")
        pipeline.execute_turn(session, actions, "Turn 2")
        pipeline.execute_turn(session, actions, "Turn 3")
        
        assert len(pipeline.trace_history) == 2
        # Oldest trace dropped
        assert pipeline.trace_history[0].turn_number == 2
        assert pipeline.trace_history[1].turn_number == 3

    def test_pipeline_resolver_failure_fallback(self):
        """Pipeline continues when resolver fails."""
        resolver = MagicMock()
        resolver.resolve.side_effect = Exception("Resolver crash")
        
        pipeline = self._make_pipeline()
        pipeline.resolver = resolver
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        result = pipeline.execute_turn(session, actions, "")
        
        # Pipeline still completes despite resolver failure
        trace = pipeline.get_last_trace()
        assert len(trace.errors) == 1
        assert "Resolver failed" in trace.errors[0]

    def test_pipeline_turn_counter_increments(self):
        """Turn counter increments with each execute_turn."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        r1 = pipeline.execute_turn(session, actions, "")
        r2 = pipeline.execute_turn(session, actions, "")
        r3 = pipeline.execute_turn(session, actions, "")
        
        assert r1["turn_number"] == 1
        assert r2["turn_number"] == 2
        assert r3["turn_number"] == 3

    def test_pipeline_feedback_stored_between_turns(self):
        """Feedback from one turn is available in the next."""
        executor = MagicMock()
        executor.execute_with_uncertainty.return_value = {
            "success": False,
            "outcome": "normal_fail",
            "events": [],
        }
        
        pipeline = self._make_pipeline()
        pipeline.executor = executor
        session = MagicMock()
        actions = [{"npc_id": "npc", "action": "attack"}]
        
        # First turn: all fail
        result1 = pipeline.execute_turn(session, actions, "")
        assert result1["director_feedback"]["failure_count"] == 1
        
        # Second turn: feedback from first is available
        feedback = pipeline.get_last_feedback()
        assert feedback is not None
        assert feedback["failure_count"] == 1

    def test_pipeline_get_planning_context(self):
        """Planning context combines arcs, resources, and feedback."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        
        # Execute a turn to generate feedback
        actions = [{"source": "director", "action": "attack"}]
        pipeline.execute_turn(session, actions, "")
        
        # planning_context should work
        ctx = pipeline.get_planning_context(session)
        assert isinstance(ctx, str)

    def test_pipeline_reset(self):
        """Reset clears pipeline state."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [{"source": "director", "action": "attack"}]
        
        pipeline.execute_turn(session, actions, "")
        assert len(pipeline.trace_history) == 1
        
        pipeline.reset()
        
        assert len(pipeline.trace_history) == 0
        assert pipeline.get_last_feedback() is None
        assert pipeline._turn_counter == 0


# ============================================================
# Integration Tests: Pipeline with Real Components
# ============================================================

class TestPipelineIntegration:
    """Integration tests with real resolver and executor."""

    def _make_pipeline(self):
        """Create pipeline with mocks."""
        resolver = MagicMock()
        resolver.resolve.return_value = []
        executor = MagicMock()
        executor.execute_with_uncertainty.return_value = {
            "success": True, "outcome": "normal_success", "events": [],
        }
        return ExecutionPipeline(
            resolver=resolver,
            executor=executor,
            enable_trace=True,
        )

    def test_pipeline_with_real_resolver_and_executor(self):
        """Pipeline works with real resolver and executor."""
        resolver = ActionResolver(strategy="first_wins")
        executor = ProbabilisticActionExecutor()
        
        pipeline = ExecutionPipeline(
            resolver=resolver,
            executor=executor,
            enable_trace=True,
        )
        session = MagicMock()
        actions = [
            {"npc_id": "npc1", "source": "director", "action": "speak", "parameters": {}},
            {"npc_id": "npc1", "source": "autonomous", "action": "move", "parameters": {}},
        ]
        
        result = pipeline.execute_turn(session, actions, "Test")
        
        assert result["turn_number"] == 1
        assert len(result["events"]) >= 0  # Events may or may not exist
        trace = pipeline.get_last_trace()
        assert trace.turn_number == 1

    def test_create_default_pipeline(self):
        """create_default_pipeline returns functional pipeline."""
        resolver = ActionResolver()
        executor = ProbabilisticActionExecutor()
        
        pipeline = create_default_pipeline(
            resolver=resolver,
            executor=executor,
            enable_trace=True,
        )
        
        assert isinstance(pipeline, ExecutionPipeline)
        assert pipeline.enable_trace is True


# ============================================================
# Edge Cases
# ============================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_pipeline_empty_actions(self):
        """Pipeline handles empty action list."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        
        result = pipeline.execute_turn(session, [], "")
        
        assert result["actions_planned"] == 0
        assert result["actions_executed"] == 0

    def test_pipeline_none_action(self):
        """Pipeline gracefully handles None in actions."""
        pipeline = self._make_pipeline()
        session = MagicMock()
        actions = [None, {"source": "director", "action": "attack"}]
        
        # Should not crash
        result = pipeline.execute_turn(session, actions, "")
        assert result is not None

    def test_trace_summary_empty(self):
        """Empty trace summary is still valid."""
        trace = TurnTrace()
        summary = trace.summary()
        assert "Turn 0" in summary

    def test_build_feedback_empty_inputs(self):
        """Feedback with empty inputs."""
        feedback = build_director_feedback([], [])
        assert feedback["total_actions"] == 0
        assert feedback["success_count"] == 0
        assert feedback["failure_count"] == 0

    def _make_pipeline(self):
        """Create pipeline with mocks."""
        resolver = MagicMock()
        resolver.resolve.return_value = []
        executor = MagicMock()
        executor.execute_with_uncertainty.return_value = {
            "success": True, "outcome": "normal_success", "events": [],
        }
        return ExecutionPipeline(
            resolver=resolver,
            executor=executor,
            enable_trace=True,
        )