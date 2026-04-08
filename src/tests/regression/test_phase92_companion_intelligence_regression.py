"""Regression tests for Phase 9.2 — Companion Intelligence Layer.

Ensures existing party functionality is not broken by 9.2 changes.
"""
import sys

import pytest


@pytest.fixture
def party_state_with_companions():
    return {
        "party_state": {
            "companions": [
                {
                    "npc_id": "c1",
                    "name": "Companion 1",
                    "hp": 100,
                    "max_hp": 100,
                    "loyalty": 0.5,
                    "morale": 0.5,
                    "status": "active",
                    "role": "guard",
                    "equipment": {},
                },
                {
                    "npc_id": "c2",
                    "name": "Companion 2",
                    "hp": 80,
                    "max_hp": 100,
                    "loyalty": 0.7,
                    "morale": 0.6,
                    "status": "active",
                    "role": "support",
                    "equipment": {},
                }
            ],
            "max_size": 3,
        }
    }


def test_ensure_party_state_idempotent():
    """Calling ensure_party_state multiple times should not change valid state."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import ensure_party_state

    ps = {"party_state": {"companions": [], "max_size": 3}}
    out1 = ensure_party_state(ps)
    out2 = ensure_party_state(out1)
    assert out1["party_state"] == out2["party_state"]


def test_add_duplicate_companion_does_not_increase_count():
    """Adding a companion with same npc_id should be a no-op."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import add_companion

    ps = {
        "party_state": {
            "companions": [{"npc_id": "npc_1", "name": "A", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "active", "role": "ally", "equipment": {}}],
            "max_size": 3,
        }
    }
    result = add_companion(ps, "npc_1", "A_dup")
    assert len(result["party_state"]["companions"]) == 1


def test_remove_companion_reduces_count():
    """Removing a companion should decrease party size."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import ensure_party_state, remove_companion

    ps = {
        "party_state": {
            "companions": [
                {"npc_id": "c1", "name": "C1", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "active", "role": "ally", "equipment": {}},
                {"npc_id": "c2", "name": "C2", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "active", "role": "ally", "equipment": {}},
            ],
            "max_size": 3,
        }
    }
    result = remove_companion(ps, "c1")
    assert len(result["party_state"]["companions"]) == 1


def test_companion_stats_normalization_on_dirty_input():
    """Ensure normalize handles missing/invalid fields gracefully."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import ensure_party_state

    ps = {
        "party_state": {
            "companions": [
                {"npc_id": "npc_1"},  # missing many fields
            ],
            "max_size": 3,
        }
    }
    out = ensure_party_state(ps)
    comp = out["party_state"]["companions"][0]
    assert "hp" in comp
    assert "max_hp" in comp
    assert "loyalty" in comp
    assert "morale" in comp
    assert "status" in comp


def test_build_party_summary_with_mixed_statuses():
    """Test party summary correctly counts active and downed companions."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import build_party_summary

    ps = {
        "party_state": {
            "companions": [
                {"npc_id": "c1", "name": "C1", "hp": 100, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "active", "role": "ally", "equipment": {}},
                {"npc_id": "c2", "name": "C2", "hp": 0, "max_hp": 100, "loyalty": 0.5, "morale": 0.5, "status": "downed", "role": "ally", "equipment": {}},
            ],
            "max_size": 3,
        }
    }
    summary = build_party_summary(ps)
    assert summary["size"] == 2
    assert summary["active_count"] == 1
    assert summary["downed_count"] == 1