"""Functional tests for Phase 9.2 — Party Intelligence Layer Routes."""
import sys

import pytest


@pytest.fixture
def minimal_player_state():
    return {
        "party_state": {
            "companions": [
                {
                    "npc_id": "npc_1",
                    "name": "Ally One",
                    "hp": 100,
                    "max_hp": 100,
                    "loyalty": 0.5,
                    "morale": 0.5,
                    "status": "active",
                    "role": "guard",
                    "equipment": {},
                }
            ],
            "max_size": 3,
        }
    }


def test_build_party_summary_returns_valid_shape(minimal_player_state):
    """Ensure build_party_summary returns a dict with expected keys."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import build_party_summary

    summary = build_party_summary(minimal_player_state)
    assert isinstance(summary, dict)
    assert "size" in summary
    assert "active_count" in summary
    assert "downed_count" in summary
    assert "avg_loyalty" in summary
    assert "avg_morale" in summary
    assert summary["size"] == 1
    assert summary["active_count"] == 1


def test_companion_loyalty_updates_persist():
    """Test loyalty delta updates correctly."""
    sys.path.insert(0, "src")
    from app.rpg.party.party_state import ensure_party_state, update_companion_loyalty

    ps = ensure_party_state({})
    ps["party_state"]["companions"] = [
        {"npc_id": "n1", "name": "X", "hp": 100, "max_hp": 100, "loyalty": 0.3, "morale": 0.5, "role": "ally", "status": "active", "equipment": {}}
    ]
    ps = update_companion_loyalty(ps, "n1", 0.1)
    comp = ps["party_state"]["companions"][0]
    assert abs(comp["loyalty"] - 0.4) < 0.001


def test_migration_v5_to_v6_adds_fields():
    """Test that migration v5→v6 adds new fields to companions."""
    sys.path.insert(0, "src")
    from app.rpg.persistence.migrations.v5_to_v6 import migrate_v5_to_v6

    v5_package = {
        "schema_version": 5,
        "state": {
            "simulation_state": {
                "player_state": {
                    "party_state": {
                        "companions": [
                            {"npc_id": "npc_1", "name": "A"}
                        ],
                        "max_size": 3,
                    }
                }
            }
        }
    }
    result = migrate_v5_to_v6(v5_package)
    assert result["schema_version"] == 6
    companions = result["state"]["simulation_state"]["player_state"]["party_state"]["companions"]
    assert len(companions) == 1
    comp = companions[0]
    assert "hp" in comp
    assert "max_hp" in comp
    assert "loyalty" in comp
    assert "morale" in comp
    assert "status" in comp
    assert "equipment" in comp


def test_migration_manager_handles_v5():
    """Test migration manager correctly processes v5 packages."""
    sys.path.insert(0, "src")
    from app.rpg.persistence.migration_manager import migrate_package_to_current

    v5_package = {
        "schema_version": 5,
        "state": {
            "simulation_state": {
                "player_state": {
                    "party_state": {
                        "companions": [
                            {"npc_id": "npc_1", "name": "A"}
                        ],
                        "max_size": 3,
                    }
                }
            }
        }
    }
    result = migrate_package_to_current(v5_package)
    assert result["schema_version"] >= 6