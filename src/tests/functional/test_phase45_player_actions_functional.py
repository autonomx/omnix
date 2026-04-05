"""Functional tests for Phase 4.5 — Player Action → Simulation Feedback.

Tests the full integration of player actions with the simulation pipeline
using the consequence-based architecture.
"""

from __future__ import annotations

import copy
import pytest


@pytest.fixture
def minimal_setup_payload():
    """Return a minimal setup payload suitable for simulation."""
    return {
        "setup_id": "test_phase45",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "A test realm",
        "premise": "Testing player actions",
        "factions": [
            {"faction_id": "f1", "name": "Red Faction", "description": "", "goals": []},
            {"faction_id": "f2", "name": "Blue Faction", "description": "", "goals": []},
        ],
        "locations": [
            {"location_id": "loc1", "name": "Capital", "description": "", "tags": []},
        ],
        "npc_seeds": [
            {"npc_id": "npc1", "name": "Rex", "role": "guard", "description": "", "goals": [], "faction_id": "f1", "location_id": "loc1"},
        ],
        "metadata": {
            "regenerated_threads": [
                {"thread_id": "thread_alpha", "name": "Border Conflict", "faction_ids": ["f1", "f2"], "location_ids": ["loc1"]},
            ],
        },
    }


class TestPlayerActionConsequenceFlow:
    """Functional tests for the consequence-based player action flow."""

    def test_intervene_thread_followed_by_simulation_step(self, minimal_setup_payload):
        """Player intervenes (queues consequence), then simulation advances."""
        from app.rpg.creator.world_simulation import (
            build_initial_simulation_state,
            step_simulation_state,
        )
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "intervene_thread", "target_id": "thread_alpha", "action_id": "act_intervene_01"}
        updated_state = apply_player_action(sim_state, action)

        # Consequence should be queued
        consequences = [c for c in updated_state["consequences"] if c["type"] == "player_intervention"]
        assert len(consequences) == 1

        # Write state back and advance
        setup["metadata"]["simulation_state"] = updated_state
        step_result = step_simulation_state(setup)
        assert step_result is not None
        assert "after_state" in step_result

    def test_support_faction_followed_by_simulation_step(self, minimal_setup_payload):
        """Player supports a faction (queues consequence), then simulation step."""
        from app.rpg.creator.world_simulation import (
            build_initial_simulation_state,
            step_simulation_state,
        )
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "support_faction", "target_id": "f1", "action_id": "act_support_01"}
        updated_state = apply_player_action(sim_state, action)

        consequences = [c for c in updated_state["consequences"] if c["type"] == "player_faction_support"]
        assert len(consequences) == 1

    def test_escalate_conflict_queues_consequence(self, minimal_setup_payload):
        """Escalating conflict queues consequence with related factions."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "escalate_conflict", "target_id": "thread_alpha", "action_id": "act_escalate_01"}
        updated_state = apply_player_action(sim_state, action)

        consequences = [c for c in updated_state["consequences"] if c["type"] == "player_escalation"]
        assert len(consequences) == 1
        assert "related_factions" in consequences[0]

    def test_events_generated_from_player_action(self, minimal_setup_payload):
        """Player actions generate events in the simulation state."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "intervene_thread", "target_id": "thread_alpha"}
        result = apply_player_action(sim_state, action)

        intervention_events = [e for e in result["events"] if e["type"] == "player_intervention"]
        assert len(intervention_events) >= 1
        assert intervention_events[0]["severity"] == "positive"

    def test_consequences_generated_from_player_action(self, minimal_setup_payload):
        """Player actions generate consequences."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "escalate_conflict", "target_id": "thread_alpha"}
        result = apply_player_action(sim_state, action)

        consequences = result["consequences"]
        assert len(consequences) >= 1

    def test_full_pipeline_action_then_advance(self, minimal_setup_payload):
        """Full pipeline: apply action → advance simulation → verify state is coherent."""
        from app.rpg.creator.world_simulation import (
            build_initial_simulation_state,
            step_simulation_state,
        )
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "intervene_thread", "target_id": "thread_alpha", "action_id": "act_full_01"}
        after_action = apply_player_action(sim_state, action)

        setup["metadata"]["simulation_state"] = after_action
        step_result = step_simulation_state(setup)

        after_state = step_result["after_state"]
        for key in ("tick", "threads", "factions", "locations"):
            assert key in after_state, f"Missing key: {key}"

    def test_action_diff_recorded_for_causality(self, minimal_setup_payload):
        """Action diff should be recorded separately for causality tracking."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "intervene_thread", "target_id": "thread_alpha", "action_id": "act_diff_01"}
        result = apply_player_action(sim_state, action)

        action_diff = result.get("action_diff", {})
        assert action_diff.get("action_type") == "intervene_thread"
        assert "player_intervention" in action_diff.get("consequences_added", [])

    def test_idempotency_in_pipeline(self, minimal_setup_payload):
        """Duplicate action_id should be silently ignored in full pipeline."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        from app.rpg.creator.world_player_actions import apply_player_action

        setup = copy.deepcopy(minimal_setup_payload)
        sim_state = build_initial_simulation_state(setup)

        action = {"type": "intervene_thread", "target_id": "thread_alpha", "action_id": "act_idem_01"}
        result1 = apply_player_action(sim_state, action)
        result2 = apply_player_action(result1, action)

        consequences1 = [c for c in result1["consequences"] if c["type"] == "player_intervention"]
        consequences2 = [c for c in result2["consequences"] if c["type"] == "player_intervention"]
        assert len(consequences1) == len(consequences2) == 1