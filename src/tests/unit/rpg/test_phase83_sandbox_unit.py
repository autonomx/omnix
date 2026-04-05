"""Phase 8.3 — Unit Tests for Sandbox/World Simulation Depth.

Tests:
- projected outcomes are bounded and deterministic
- location trend updates clamp correctly
- thread trajectory changes correctly
- faction trend updates correctly
- rumor heat feedback increments correctly
- world consequences capped to 100
"""
from __future__ import annotations

import pytest

from app.rpg.sandbox import (
    project_outcomes_from_state,
    update_location_trends,
    update_thread_trends,
    update_faction_trends,
    update_rumor_feedback,
    build_world_consequences,
)


class TestOutcomeProjection:
    """Tests for outcome projection."""

    def test_empty_state_returns_empty_list(self):
        result = project_outcomes_from_state({})
        assert result == []

    def test_bounded_to_24_max(self):
        state = {
            "tick": 1,
            "events": [{"type": "betrayal", "target_id": "t", "location_id": "l", "faction_id": "f", "summary": "s"}] * 30,
        }
        result = project_outcomes_from_state(state)
        assert len(result) <= 24

    def test_betrayal_emits_faction_pressure(self):
        state = {
            "tick": 1,
            "events": [{"type": "betrayal", "target_id": "t1", "location_id": "l1", "faction_id": "f1", "summary": "betrayal"}],
        }
        result = project_outcomes_from_state(state)
        assert len(result) == 1
        assert result[0]["type"] == "faction_pressure"
        assert result[0]["target_id"] == "f1"

    def test_player_support_emits_location_stabilization(self):
        state = {
            "tick": 1,
            "events": [{"type": "player_support", "target_id": "t1", "location_id": "l1", "faction_id": "f1", "summary": "support"}],
        }
        result = project_outcomes_from_state(state)
        assert len(result) == 1
        assert result[0]["type"] == "location_stabilization"

    def test_encounter_resolution_emits_outcome(self):
        state = {
            "tick": 1,
            "player_state": {"encounter_state": {"status": "resolved", "scene_id": "s1"}},
        }
        result = project_outcomes_from_state(state)
        assert len(result) == 1
        assert result[0]["type"] == "encounter_resolution"

    def test_deterministic_same_input_same_output(self):
        state = {
            "tick": 5,
            "events": [{"type": "betrayal", "target_id": "t", "location_id": "l", "faction_id": "f", "summary": "s"}],
        }
        r1 = project_outcomes_from_state(state)
        r2 = project_outcomes_from_state(state)
        assert r1 == r2


class TestLocationDynamics:
    """Tests for location dynamics."""

    def test_stabilization_increases_stability_decreases_danger(self):
        state = {"tick": 1, "sandbox_state": {"location_trends": {}}}
        outcomes = [{"type": "location_stabilization", "target_id": "loc1", "location_id": "loc1"}]
        result = update_location_trends(state, outcomes)
        trends = result["sandbox_state"]["location_trends"]
        assert trends["loc1"]["stability"] == 0.6
        assert trends["loc1"]["danger"] == 0.4

    def test_faction_pressure_increases_danger(self):
        state = {"tick": 1, "sandbox_state": {"location_trends": {}}}
        outcomes = [{"type": "faction_pressure", "target_id": "loc1", "location_id": "loc1"}]
        result = update_location_trends(state, outcomes)
        trends = result["sandbox_state"]["location_trends"]
        assert trends["loc1"]["danger"] == 0.55

    def test_danger_clamped_at_1_0(self):
        state = {"tick": 1, "sandbox_state": {"location_trends": {"loc1": {"stability": 0.5, "danger": 1.0}}}}
        outcomes = [{"type": "faction_pressure", "target_id": "loc1", "location_id": "loc1"}] * 20
        result = update_location_trends(state, outcomes)
        trends = result["sandbox_state"]["location_trends"]
        assert trends["loc1"]["danger"] == 1.0

    def test_stability_clamped_at_1_0(self):
        state = {"tick": 1, "sandbox_state": {"location_trends": {"loc1": {"stability": 1.0, "danger": 0.5}}}}
        outcomes = [{"type": "location_stabilization", "target_id": "loc1", "location_id": "loc1"}] * 20
        result = update_location_trends(state, outcomes)
        trends = result["sandbox_state"]["location_trends"]
        assert trends["loc1"]["stability"] == 1.0
        assert trends["loc1"]["danger"] == 0.0


class TestThreadEvolution:
    """Tests for thread evolution."""

    def test_resolve_trajectory(self):
        state = {"tick": 1, "sandbox_state": {"thread_trends": {}}}
        outcomes = [{"type": "thread_shift", "target_id": "t1", "summary": "issue resolved"}]
        result = update_thread_trends(state, outcomes)
        trends = result["sandbox_state"]["thread_trends"]
        assert trends["t1"]["trajectory"] == "resolved"
        assert trends["t1"]["intensity"] == 0.2

    def test_branching_trajectory(self):
        state = {"tick": 1, "sandbox_state": {"thread_trends": {}}}
        outcomes = [{"type": "thread_shift", "target_id": "t1", "summary": "new branch"}]
        result = update_thread_trends(state, outcomes)
        trends = result["sandbox_state"]["thread_trends"]
        assert trends["t1"]["trajectory"] == "branching"
        assert trends["t1"]["intensity"] == 0.7

    def test_default_escalating(self):
        state = {"tick": 1, "sandbox_state": {"thread_trends": {}}}
        outcomes = [{"type": "thread_shift", "target_id": "t1", "summary": "something else"}]
        result = update_thread_trends(state, outcomes)
        trends = result["sandbox_state"]["thread_trends"]
        assert trends["t1"]["trajectory"] == "escalating"
        assert trends["t1"]["intensity"] == 0.6


class TestFactionDynamics:
    """Tests for faction dynamics."""

    def test_faction_pressure_increases_aggression_and_momentum(self):
        state = {"tick": 1, "sandbox_state": {"faction_trends": {}}}
        outcomes = [{"type": "faction_pressure", "target_id": "faction1"}]
        result = update_faction_trends(state, outcomes)
        trends = result["sandbox_state"]["faction_trends"]
        assert trends["faction1"]["aggression"] == 0.6
        assert trends["faction1"]["momentum"] == 0.55

    def test_non_faction_outcomes_ignored(self):
        state = {"tick": 1, "sandbox_state": {"faction_trends": {}}}
        outcomes = [{"type": "location_stabilization", "target_id": "loc1"}]
        result = update_faction_trends(state, outcomes)
        trends = result["sandbox_state"]["faction_trends"]
        assert trends == {}


class TestRumorFeedback:
    """Tests for rumor feedback."""

    def test_rumor_heat_increments_on_match(self):
        state = {
            "tick": 1,
            "social_state": {"rumors": [{"subject_id": "s1", "heat": 0}]},
        }
        outcomes = [{"type": "faction_pressure", "target_id": "s1"}]
        result = update_rumor_feedback(state, outcomes)
        assert result["social_state"]["rumors"][0]["heat"] == 1

    def test_rumor_heat_capped_at_3(self):
        state = {
            "tick": 1,
            "social_state": {"rumors": [{"subject_id": "s1", "heat": 3}]},
        }
        outcomes = [{"type": "faction_pressure", "target_id": "s1"}] * 5
        result = update_rumor_feedback(state, outcomes)
        assert result["social_state"]["rumors"][0]["heat"] == 3

    def test_no_match_no_heat_change(self):
        state = {
            "tick": 1,
            "social_state": {"rumors": [{"subject_id": "s1", "heat": 0}]},
        }
        outcomes = [{"type": "faction_pressure", "target_id": "different"}]
        result = update_rumor_feedback(state, outcomes)
        assert result["social_state"]["rumors"][0]["heat"] == 0


class TestWorldConsequences:
    """Tests for world consequence builder."""

    def test_location_stabilization_maps_to_positive(self):
        state = {"tick": 1, "sandbox_state": {"world_consequences": []}}
        outcomes = [{"type": "location_stabilization", "target_id": "loc1", "summary": "s"}]
        result = build_world_consequences(state, outcomes)
        consequences = result["sandbox_state"]["world_consequences"]
        assert len(consequences) == 1
        assert consequences[0]["severity"] == "positive"
        assert consequences[0]["type"] == "location_shift"

    def test_faction_pressure_maps_to_negative(self):
        state = {"tick": 1, "sandbox_state": {"world_consequences": []}}
        outcomes = [{"type": "faction_pressure", "target_id": "f1", "summary": "s"}]
        result = build_world_consequences(state, outcomes)
        consequences = result["sandbox_state"]["world_consequences"]
        assert consequences[0]["severity"] == "negative"
        assert consequences[0]["type"] == "faction_shift"

    def test_capped_at_100(self):
        state = {"tick": 1, "sandbox_state": {"world_consequences": []}}
        outcomes = [{"type": "faction_pressure", "target_id": f"f{i}", "summary": f"s{i}"} for i in range(150)]
        result = build_world_consequences(state, outcomes)
        consequences = result["sandbox_state"]["world_consequences"]
        assert len(consequences) == 100