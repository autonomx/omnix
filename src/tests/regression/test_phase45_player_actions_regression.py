"""Regression tests for Phase 4.5 — Player Action → Simulation Feedback.

Ensures that changes to the player action system do not break existing behavior.
Updated for the consequence-based architecture (actions queue consequences,
which are then consumed by the effects system on the next tick).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def baseline_sim_state():
    """Baseline simulation state for regression comparison."""
    return {
        "tick": 0,
        "threads": {
            "t1": {"pressure": 3, "status": "active", "faction_ids": ["f1", "f2"]},
            "t2": {"pressure": 1, "status": "low"},
        },
        "factions": {
            "f1": {"pressure": 2, "status": "watchful"},
            "f2": {"pressure": 0, "status": "stable"},
        },
        "locations": {
            "l1": {"heat": 2, "status": "active"},
        },
        "history": [],
        "events": [],
        "consequences": [],
        "applied_actions": [],
    }


# ---------------------------------------------------------------------------
# Regression Tests (consequence-based)
# ---------------------------------------------------------------------------


class TestPlayerActionRegression:
    """Ensure player action behavior remains stable across releases."""

    def test_intervene_thread_consequence_magnitude_is_stable(self, baseline_sim_state):
        """``intervene_thread`` should always produce consequence with magnitude -2."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_intervention"]
        assert len(consequences) == 1
        assert consequences[0]["magnitude"] == -2, (
            "Magnitude for intervene_thread consequence should remain -2"
        )

    def test_support_faction_consequence_magnitude_is_stable(self, baseline_sim_state):
        """``support_faction`` should always produce consequence with magnitude -1."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "support_faction", "target_id": "f1"}
        result = apply_player_action(baseline_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_faction_support"]
        assert len(consequences) == 1
        assert consequences[0]["magnitude"] == -1, (
            "Magnitude for support_faction consequence should remain -1"
        )

    def test_escalate_conflict_consequence_magnitude_is_stable(self, baseline_sim_state):
        """``escalate_conflict`` should always produce consequence with magnitude +2."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "escalate_conflict", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_escalation"]
        assert len(consequences) == 1
        assert consequences[0]["magnitude"] == 2, (
            "Magnitude for escalate_conflict consequence should remain +2"
        )
        # Should include related factions from thread metadata
        assert "related_factions" in consequences[0]

    def test_pressure_values_not_mutated_directly(self, baseline_sim_state):
        """Actions should NOT change pressure values directly (consequence-based)."""
        from app.rpg.creator.world_player_actions import apply_player_action

        orig_t1_pressure = baseline_sim_state["threads"]["t1"]["pressure"]
        orig_f1_pressure = baseline_sim_state["factions"]["f1"]["pressure"]

        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        assert result["threads"]["t1"]["pressure"] == orig_t1_pressure, (
            "Pressure should not be mutated directly"
        )
        assert result["factions"]["f1"]["pressure"] == orig_f1_pressure, (
            "Faction pressure should not be mutated directly"
        )

    def test_events_structure_stable(self, baseline_sim_state):
        """Events list should always be present and appended to."""
        from app.rpg.creator.world_player_actions import apply_player_action

        baseline_sim_state["events"] = [{"type": "pre_existing"}]
        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "pre_existing"
        assert result["events"][1]["type"] == "player_intervention"

    def test_consequences_structure_stable(self, baseline_sim_state):
        """Consequences list should always be present and appended to."""
        from app.rpg.creator.world_player_actions import apply_player_action

        baseline_sim_state["consequences"] = [{"type": "pre_existing"}]
        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        assert len(result["consequences"]) == 2

    def test_unknown_action_type_does_not_corrupt_state(self, baseline_sim_state):
        """Unknown actions should add an event but leave pressures intact."""
        from app.rpg.creator.world_player_actions import apply_player_action

        orig_t1_pressure = baseline_sim_state["threads"]["t1"]["pressure"]
        action = {"type": "bogus_action", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        assert result["threads"]["t1"]["pressure"] == orig_t1_pressure
        assert any(e["type"] == "unknown_action" for e in result["events"])

    def test_determinism_same_input_same_output(self, baseline_sim_state):
        """Same input should always produce same output."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1"}
        result1 = apply_player_action(baseline_sim_state, action)
        result2 = apply_player_action(baseline_sim_state, action)

        assert len(result1["consequences"]) == len(result2["consequences"])
        c1 = result1["consequences"][-1]
        c2 = result2["consequences"][-1]
        assert c1["magnitude"] == c2["magnitude"]

    def test_action_diff_recorded_for_causality(self, baseline_sim_state):
        """action_diff key should provide causality tracking."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1", "action_id": "reg_001"}
        result = apply_player_action(baseline_sim_state, action)

        action_diff = result.get("action_diff", {})
        assert action_diff is not None
        assert action_diff.get("action_type") == "intervene_thread"
        assert action_diff.get("target_id") == "t1"
        assert len(action_diff.get("consequences_added", [])) == 1

    def test_idempotency_protection_stable(self, baseline_sim_state):
        """Duplicate action_id should be silently ignored."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1", "action_id": "idem_reg"}
        result1 = apply_player_action(baseline_sim_state, action)
        result2 = apply_player_action(result1, action)

        c1 = [c for c in result1["consequences"] if c["type"] == "player_intervention"]
        c2 = [c for c in result2["consequences"] if c["type"] == "player_intervention"]
        assert len(c1) == len(c2) == 1

    def test_escalate_scoped_to_related_factions(self, baseline_sim_state):
        """Escalation should only affect factions listed in thread metadata."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "escalate_conflict", "target_id": "t1"}
        result = apply_player_action(baseline_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_escalation"]
        assert len(consequences) == 1
        rf = consequences[0].get("related_factions", [])
        # Should include f1 and f2 from thread faction_ids
        assert "f1" in rf
        assert "f2" in rf

    def test_service_endpoint_importable(self):
        """The service endpoint should be importable without errors."""
        from app.rpg.services.adventure_builder_service import apply_player_action_endpoint
        assert callable(apply_player_action_endpoint)

    def test_creator_routes_include_simulation_action(self):
        """The creator routes should expose the simulation/action endpoint."""
        from app.rpg import creator_routes
        # Check that the route function exists
        assert hasattr(creator_routes, "simulation_action"), (
            "simulation_action route should exist on creator_routes module"
        )