"""Phase 8.3 — Regression Tests for Sandbox/World Simulation Depth.

Ensures existing functionality continues to work after Phase 8.3 changes.
"""
from __future__ import annotations

import pytest

from app.rpg.creator.world_simulation import (
    step_simulation_state,
    build_initial_simulation_state,
)
from app.rpg.sandbox import (
    project_outcomes_from_state,
    update_location_trends,
    update_thread_trends,
    update_faction_trends,
    update_rumor_feedback,
    build_world_consequences,
)


class TestSandboxRegression:
    """Regression tests to ensure Phase 8.3 doesn't break existing behavior."""

    def test_step_simulation_state_returns_expected_keys(self):
        """step_simulation_state should return all expected keys."""
        setup = {
            "metadata": {},
            "locations": [{"location_id": "loc1", "name": "Loc1"}],
            "factions": [{"faction_id": "f1", "name": "F1"}],
            "npc_seeds": [],
        }
        result = step_simulation_state(setup)
        expected_keys = {
            "next_setup", "before_state", "after_state", "after_state_base",
            "simulation_diff", "base_diff", "effect_applied_diff", "summary",
            "events", "consequences", "effect_diff", "incident_diff", "reaction_diff",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_simulation_state_has_tick_incremented(self):
        """After step, tick should be incremented."""
        setup = {
            "metadata": {},
            "locations": [{"location_id": "loc1", "name": "Loc1"}],
            "factions": [{"faction_id": "f1", "name": "F1"}],
            "npc_seeds": [],
        }
        result = step_simulation_state(setup)
        assert result["after_state"]["tick"] == 1

    def test_project_outcomes_deterministic(self):
        """Same input should produce same output every time."""
        state = {
            "tick": 1,
            "events": [{"type": "betrayal", "target_id": "t", "location_id": "l", "faction_id": "f", "summary": "s"}],
        }
        r1 = project_outcomes_from_state(state)
        r2 = project_outcomes_from_state(state)
        assert r1 == r2

    def test_location_trends_preserves_existing(self):
        """Existing location trends should be preserved when no matching outcomes."""
        state = {"tick": 1, "sandbox_state": {"location_trends": {"loc1": {"stability": 0.5, "danger": 0.5}}}}
        outcomes = [{"type": "faction_pressure", "target_id": "f1", "location_id": ""}]  # Empty location_id
        result = update_location_trends(state, outcomes)
        trends = result["sandbox_state"]["location_trends"]
        # Empty location_id falls back to target_id, so f1 is added, loc1 remains
        assert "loc1" in trends
        assert trends["loc1"]["stability"] == 0.5
        assert trends["loc1"]["danger"] == 0.5

    def test_world_consequences_grow_monotonically(self):
        """World consequences should only grow, not shrink (within cap)."""
        state = {"tick": 1, "sandbox_state": {"world_consequences": []}}
        outcomes1 = [{"type": "faction_pressure", "target_id": "f1", "summary": "s1"}]
        result1 = build_world_consequences(state, outcomes1)
        c1 = len(result1["sandbox_state"]["world_consequences"])

        state2 = result1
        state2["tick"] = 2
        outcomes2 = [{"type": "faction_pressure", "target_id": "f2", "summary": "s2"}]
        result2 = build_world_consequences(state2, outcomes2)
        c2 = len(result2["sandbox_state"]["world_consequences"])

        assert c2 >= c1

    def test_integration_with_scenes(self):
        """Scenes should include sandbox_summary after generation."""
        from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation

        setup = {
            "metadata": {},
            "locations": [{"location_id": "loc1", "name": "Loc1"}],
            "factions": [{"faction_id": "f1", "name": "F1"}],
            "npc_seeds": [],
        }
        result = step_simulation_state(setup)
        state = result["after_state"]
        scenes = generate_scenes_from_simulation(state)
        # Scenes should include sandbox_summary from state
        if scenes:
            for scene in scenes:
                assert "sandbox_summary" in scene

    def test_encounter_log_has_type_and_target(self):
        """Encounter log entries should have log_type and target_id."""
        from app.rpg.encounter import EncounterResolver

        resolver = EncounterResolver()
        encounter_state = {
            "participants": [
                {"actor_id": "player", "side": "player", "hp": 10, "stress": 0},
                {"actor_id": "enemy1", "side": "enemy", "hp": 5, "stress": 0},
            ],
            "turn_index": -1,
            "round": 1,
            "log": [],
            "active_actor_id": "",
        }
        encounter_state = resolver.start(encounter_state)
        encounter_state["active_actor_id"] = "player"
        encounter_state = resolver.apply_player_action(encounter_state, "attack", "enemy1")

        assert len(encounter_state["log"]) >= 1
        log_entry = encounter_state["log"][0]
        assert "log_type" in log_entry
        assert "target_id" in log_entry
        assert log_entry["log_type"] == "attack"
        assert log_entry["target_id"] == "enemy1"

    def test_rumor_feedback_preserves_rumor_list_size(self):
        """Rumor list should be capped at 64."""
        state = {
            "tick": 1,
            "social_state": {"rumors": [{"subject_id": f"s{i}", "heat": 0} for i in range(100)]},
        }
        outcomes = [{"type": "faction_pressure", "target_id": "s1"}]
        result = update_rumor_feedback(state, outcomes)
        assert len(result["social_state"]["rumors"]) <= 64