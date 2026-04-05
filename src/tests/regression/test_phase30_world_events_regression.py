"""Phase 30 — World Events & Consequences Regression Tests.

These tests verify that the events/consequences layer integrates correctly
with the rest of the creator pipeline and that existing behaviour is not
broken.
"""

import pytest

from app.rpg.creator.world_simulation import step_simulation_state


def _minimal_setup() -> dict:
    return {
        "setup_id": "reg_test_1",
        "metadata": {"regenerated_threads": []},
        "factions": [],
        "locations": [],
        "npc_seeds": [],
    }


# ---------------------------------------------------------------------------
# Regression: stepping with no content should not raise
# ---------------------------------------------------------------------------


def test_step_empty_setup_no_error():
    """Empty setup should step cleanly without raising."""
    result = step_simulation_state(_minimal_setup())
    assert result["after_state"]["tick"] == 1


# ---------------------------------------------------------------------------
# Regression: deterministic identity — same input → same output
# ---------------------------------------------------------------------------


def test_determinism_identical_runs():
    """Two calls with the same input should produce identical step hashes."""
    a = step_simulation_state(_minimal_setup())
    b = step_simulation_state(_minimal_setup())
    assert a["after_state"]["step_hash"] == b["after_state"]["step_hash"]


# ---------------------------------------------------------------------------
# Regression: next_setup is a deep copy, not a mutated original
# ---------------------------------------------------------------------------


def test_next_setup_is_copy():
    original = _minimal_setup()
    original["title"] = "original_title"
    result = step_simulation_state(original)
    next_setup = result["next_setup"]

    # Mutating the result should not affect the original
    meta = next_setup.get("metadata", {})
    meta["test_mutation"] = True
    assert "test_mutation" not in original.get("metadata", {})


# ---------------------------------------------------------------------------
# Regression: history is capped
# ---------------------------------------------------------------------------


def test_history_capped_at_max():
    """Run many steps and verify history length is bounded."""
    MAX_HISTORY = 20
    setup = _minimal_setup()

    for i in range(30):
        result = step_simulation_state(setup)
        setup = result["next_setup"]

    history = result["after_state"].get("history", [])
    assert len(history) <= MAX_HISTORY