"""Phase 9.1 — Regression tests for Party System and save compatibility."""
from __future__ import annotations

import pytest

from app.rpg.party import ensure_party_state, add_companion, remove_companion, get_active_companions
from app.rpg.party.companion_ai import run_companion_turns
from app.rpg.persistence.migrations.v4_to_v5 import migrate_v4_to_v5


class TestPartySaveCompatibility:
    """Ensure party state survives migration and round-tripping."""

    def test_migrate_v4_to_v5_adds_party_state(self):
        package = {
            "schema_version": 4,
            "simulation_state": {
                "player_state": {},
            },
        }
        result = migrate_v4_to_v5(package)
        assert result["schema_version"] == 5
        assert "party_state" in result["simulation_state"]["player_state"]

    def test_migrate_v4_to_v5_does_not_overwrite_companions(self):
        package = {
            "schema_version": 4,
            "simulation_state": {
                "player_state": {
                    "party_state": {
                        "companions": [{"npc_id": "npc_1", "name": "Existing"}],
                        "max_size": 5,
                    },
                },
            },
        }
        result = migrate_v4_to_v5(package)
        assert len(result["simulation_state"]["player_state"]["party_state"]["companions"]) == 1
        assert result["simulation_state"]["player_state"]["party_state"]["max_size"] == 5

    def test_migrate_v4_to_v5_missing_simulation_state(self):
        package = {"schema_version": 4}
        result = migrate_v4_to_v5(package)
        assert result["schema_version"] == 5
        assert "party_state" in result["simulation_state"]["player_state"]

    def test_migrate_v4_to_v5_missing_player_state(self):
        package = {"schema_version": 4, "simulation_state": {}}
        result = migrate_v4_to_v5(package)
        assert result["schema_version"] == 5
        assert "party_state" in result["simulation_state"]["player_state"]


class TestPartyRegression:
    """Ensure party state does not break existing functionality."""

    def test_empty_player_state_has_party_after_ensure(self):
        player_state = {}
        result = ensure_party_state(player_state)
        assert "party_state" in result
        assert result["party_state"]["companions"] == []
        assert result["party_state"]["max_size"] == 3

    def test_add_companion_then_remove_roundtrip(self):
        player_state = {}
        result = add_companion(player_state, "npc_1", "Alice")
        result = add_companion(result, "npc_2", "Bob")
        assert len(get_active_companions(result)) == 2
        result = remove_companion(result, "npc_1")
        assert len(get_active_companions(result)) == 1

    def test_companion_ai_handles_missing_player_state(self):
        simulation_state = {}
        encounter_state = {"log": []}
        result = run_companion_turns(simulation_state, encounter_state)
        assert result == encounter_state

    def test_companion_ai_handles_missing_encounter_log(self):
        player_state = add_companion({}, "npc_1", "Alice")
        simulation_state = {"player_state": player_state}
        encounter_state = {}
        result = run_companion_turns(simulation_state, encounter_state)
        assert "log" in result

    def test_party_state_isolated_from_inventory(self):
        player_state = {
            "inventory_state": {"items": ["gold_coin"], "equipment": {}, "capacity": 50},
        }
        result = ensure_party_state(player_state)
        assert "inventory_state" in result
        assert "party_state" in result
        assert result["inventory_state"]["items"] == ["gold_coin"]