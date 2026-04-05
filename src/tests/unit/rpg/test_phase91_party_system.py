"""Phase 9.1 — Unit tests for Party / Companion System."""
from __future__ import annotations

import pytest

from app.rpg.party import (
    ensure_party_state,
    add_companion,
    remove_companion,
    get_active_companions,
)
from app.rpg.party.companion_ai import run_companion_turns


# ---------------------------------------------------------------------------
# Party State Tests
# ---------------------------------------------------------------------------

class TestEnsurePartyState:
    def test_ensure_party_state_creates_party_state(self):
        player_state = {}
        result = ensure_party_state(player_state)
        assert "party_state" in result
        assert result["party_state"]["companions"] == []
        assert result["party_state"]["max_size"] == 3

    def test_ensure_party_state_idempotent(self):
        player_state = {"party_state": {"companions": [{"npc_id": "a"}], "max_size": 2}}
        result = ensure_party_state(player_state)
        assert result["party_state"]["companions"] == [{"npc_id": "a"}]
        assert result["party_state"]["max_size"] == 2

    def test_ensure_party_state_handles_dirty_input(self):
        player_state = {"party_state": None}
        result = ensure_party_state(player_state)
        assert "party_state" in result
        assert result["party_state"]["companions"] == []


# ---------------------------------------------------------------------------
# Add Companion Tests
# ---------------------------------------------------------------------------

class TestAddCompanion:
    def test_add_companion_success(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        companions = get_active_companions(result)
        assert len(companions) == 1
        assert companions[0]["npc_id"] == "npc_1"
        assert companions[0]["name"] == "Alice"
        assert companions[0]["hp"] == 100
        assert companions[0]["loyalty"] == 0.5
        assert companions[0]["role"] == "ally"

    def test_add_companion_duplicate_rejected(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        result = add_companion(result, "npc_1", "Alice")
        companions = get_active_companions(result)
        assert len(companions) == 1

    def test_add_companion_respects_max_size(self):
        player_state = {"party_state": {"companions": [], "max_size": 2}}
        result = add_companion(player_state, "npc_1", "Alice")
        result = add_companion(result, "npc_2", "Bob")
        result = add_companion(result, "npc_3", "Charlie")
        companions = get_active_companions(result)
        assert len(companions) == 2

    def test_add_multiple_companions(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        result = add_companion(result, "npc_2", "Bob")
        result = add_companion(result, "npc_3", "Charlie")
        companions = get_active_companions(result)
        assert len(companions) == 3


# ---------------------------------------------------------------------------
# Remove Companion Tests
# ---------------------------------------------------------------------------

class TestRemoveCompanion:
    def test_remove_companion_success(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        result = remove_companion(result, "npc_1")
        companions = get_active_companions(result)
        assert len(companions) == 0

    def test_remove_companion_not_present(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        result = remove_companion(result, "npc_2")
        companions = get_active_companions(result)
        assert len(companions) == 1

    def test_remove_companion_from_empty(self):
        player_state = {}
        result = remove_companion(player_state, "npc_1")
        companions = get_active_companions(result)
        assert len(companions) == 0


# ---------------------------------------------------------------------------
# Get Active Companions Tests
# ---------------------------------------------------------------------------

class TestGetActiveCompanions:
    def test_get_active_companions_empty(self):
        player_state = {}
        companions = get_active_companions(player_state)
        assert companions == []

    def test_get_active_companions_returns_copy(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        companions1 = get_active_companions(result)
        companions1.append({"npc_id": "npc_2", "name": "Bob"})
        companions2 = get_active_companions(result)
        assert len(companions2) == 1


# ---------------------------------------------------------------------------
# Companion AI Tests
# ---------------------------------------------------------------------------

class TestCompanionAI:
    def test_run_companion_turns_empty(self):
        simulation_state = {"player_state": {}}
        encounter_state = {}
        result = run_companion_turns(simulation_state, encounter_state)
        assert result.get("log") == []

    def test_run_companion_turns_adds_log_entries(self):
        player_state = add_companion({}, "npc_1", "Alice")
        simulation_state = {"player_state": player_state}
        encounter_state = {"log": []}
        result = run_companion_turns(simulation_state, encounter_state)
        assert len(result["log"]) == 1
        assert result["log"][0]["type"] == "companion_action"
        assert result["log"][0]["npc_id"] == "npc_1"

    def test_run_companion_turns_limited_to_3(self):
        player_state = add_companion({}, "npc_1", "Alice")
        player_state = add_companion(player_state, "npc_2", "Bob")
        player_state = add_companion(player_state, "npc_3", "Charlie")
        player_state = add_companion(player_state, "npc_4", "Dave")
        simulation_state = {"player_state": player_state}
        encounter_state = {"log": []}
        result = run_companion_turns(simulation_state, encounter_state)
        assert len(result["log"]) == 3

    def test_run_companion_turns_preserves_existing_log(self):
        player_state = add_companion({}, "npc_1", "Alice")
        simulation_state = {"player_state": player_state}
        encounter_state = {"log": [{"type": "player_action"}]}
        result = run_companion_turns(simulation_state, encounter_state)
        assert len(result["log"]) == 2
        assert result["log"][0]["type"] == "player_action"