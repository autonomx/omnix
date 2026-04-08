"""Unit tests for Phase 4.5 — Player Action → Simulation Feedback.

Tests the consequence-based player action system.
"""

from __future__ import annotations

import copy

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_sim_state():
    """Return a baseline simulation state for testing."""
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
# Tests — apply_player_action (consequence-based)
# ---------------------------------------------------------------------------


class TestApplyPlayerAction:
    """Unit tests for ``apply_player_action`` (consequence-based)."""

    def test_intervene_thread_appends_consequence(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_intervention"]
        assert len(consequences) == 1
        assert consequences[0]["target_id"] == "t1"
        assert consequences[0]["magnitude"] == -2
        assert consequences[0]["origin"] == "player_action"

    def test_intervene_thread_appends_event(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        events = [e for e in result["events"] if e["type"] == "player_intervention"]
        assert len(events) == 1
        assert events[0]["severity"] == "positive"

    def test_support_faction_appends_consequence(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "support_faction", "target_id": "f1"}
        result = apply_player_action(sample_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_faction_support"]
        assert len(consequences) == 1
        assert consequences[0]["magnitude"] == -1
        assert consequences[0]["origin"] == "player_action"

    def test_escalate_conflict_appends_consequence_with_factions(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "escalate_conflict", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        consequences = [c for c in result["consequences"] if c["type"] == "player_escalation"]
        assert len(consequences) == 1
        assert consequences[0]["magnitude"] == 2
        assert "related_factions" in consequences[0]
        # Should include factions from thread metadata
        assert "f1" in consequences[0]["related_factions"]
        assert "f2" in consequences[0]["related_factions"]

    def test_escalate_conflict_event_has_negative_severity(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "escalate_conflict", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        events = [e for e in result["events"] if e["type"] == "player_escalation"]
        assert len(events) == 1
        assert events[0]["severity"] == "negative"

    def test_does_not_mutate_pressure_directly(self, sample_sim_state):
        """Action should append consequences, not change pressure values."""
        from app.rpg.creator.world_player_actions import apply_player_action

        orig_pressure = sample_sim_state["threads"]["t1"]["pressure"]
        action = {"type": "intervene_thread", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        # Pressure should remain unchanged (consequences are queued, not applied)
        assert result["threads"]["t1"]["pressure"] == orig_pressure

    def test_idempotency_with_action_id(self, sample_sim_state):
        """Same action_id should be silently ignored on second call."""
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1", "action_id": "act_001"}
        result1 = apply_player_action(sample_sim_state, action)

        # Simulate a second submission with same action_id
        result2 = apply_player_action(result1, action)

        # Consequences count should not increase
        consequences1 = [c for c in result1["consequences"] if c["type"] == "player_intervention"]
        consequences2 = [c for c in result2["consequences"] if c["type"] == "player_intervention"]
        assert len(consequences1) == len(consequences2)

    def test_action_id_recorded_in_state(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1", "action_id": "act_xyz"}
        result = apply_player_action(sample_sim_state, action)

        assert "act_xyz" in result.get("applied_actions", [])

    def test_action_diff_recorded(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "t1", "action_id": "act_diff_test"}
        result = apply_player_action(sample_sim_state, action)

        action_diff = result.get("action_diff", {})
        assert action_diff.get("action_type") == "intervene_thread"
        assert action_diff.get("target_id") == "t1"
        assert len(action_diff.get("consequences_added", [])) == 1

    def test_unknown_target_produces_unknown_event(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "intervene_thread", "target_id": "nonexistent"}
        result = apply_player_action(sample_sim_state, action)

        unknown_events = [e for e in result["events"] if e["type"] == "unknown_action"]
        assert len(unknown_events) == 1

    def test_unknown_action_type_produces_event(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": "random_action", "target_id": "t1"}
        result = apply_player_action(sample_sim_state, action)

        unknown_events = [e for e in result["events"] if e["type"] == "unknown_action"]
        assert len(unknown_events) == 1

    def test_does_not_mutate_original_state(self, sample_sim_state):
        import copy

        from app.rpg.creator.world_player_actions import apply_player_action

        original = copy.deepcopy(sample_sim_state)
        action = {"type": "intervene_thread", "target_id": "t1"}
        apply_player_action(sample_sim_state, action)

        assert sample_sim_state == original

    def test_empty_action_type_no_crash(self, sample_sim_state):
        from app.rpg.creator.world_player_actions import apply_player_action

        action = {"type": ""}
        result = apply_player_action(sample_sim_state, action)
        assert "threads" in result
        assert "events" in result

    def test_missing_keys_handled(self):
        from app.rpg.creator.world_player_actions import apply_player_action

        state = {}
        action = {}
        result = apply_player_action(state, action)
        assert isinstance(result, dict)

    def test_consequences_have_origin_field(self, sample_sim_state):
        """All consequences from player actions should have origin='player_action'."""
        from app.rpg.creator.world_player_actions import apply_player_action

        for typ in ["intervene_thread", "support_faction", "escalate_conflict"]:
            state = copy.deepcopy(sample_sim_state)
            if typ in ("intervene_thread", "escalate_conflict"):
                action = {"type": typ, "target_id": "t1"}
            else:
                action = {"type": typ, "target_id": "f1"}
            result = apply_player_action(state, action)
            for c in result["consequences"]:
                assert c.get("origin") == "player_action"