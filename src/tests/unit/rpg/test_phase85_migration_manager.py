"""Unit tests for Phase 8.5 migration manager and migrations."""
import pytest

from app.rpg.persistence.migrations.v1_to_v2 import migrate_v1_to_v2
from app.rpg.persistence.migrations.v2_to_v3 import migrate_v2_to_v3
from app.rpg.persistence.migration_manager import migrate_package_to_current
from app.rpg.persistence.package_validator import validate_save_package
from app.rpg.persistence.save_schema import CURRENT_RPG_SCHEMA_VERSION, PACKAGE_TYPE


class TestMigrateV1ToV2:
    """Tests for v1 -> v2 migration."""

    def test_migrate_v1_to_v2_adds_missing_keys(self):
        v1_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "world": "test_world",
                }
            },
        }
        result = migrate_v1_to_v2(v1_package)
        sim_state = result["state"]["simulation_state"]
        assert "player_state" in sim_state
        assert "social_state" in sim_state
        assert "debug_meta" in sim_state
        assert "gm_overrides" in sim_state
        assert result["schema_version"] == 2

    def test_migrate_v1_to_v2_preserves_existing_data(self):
        v1_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "world": "test_world",
                    "existing_key": "value",
                }
            },
        }
        result = migrate_v1_to_v2(v1_package)
        sim_state = result["state"]["simulation_state"]
        assert sim_state["world"] == "test_world"
        assert sim_state["existing_key"] == "value"

    def test_migrate_v1_to_v2_handles_none_input(self):
        result = migrate_v1_to_v2(None)
        assert isinstance(result, dict)
        assert result["schema_version"] == 2

    def test_migrate_v1_to_v2_does_not_overwrite_existing_keys(self):
        v1_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "player_state": {"existing": "data"},
                    "social_state": {"existing": "social"},
                }
            },
        }
        result = migrate_v1_to_v2(v1_package)
        sim_state = result["state"]["simulation_state"]
        assert sim_state["player_state"] == {"existing": "data"}
        assert sim_state["social_state"] == {"existing": "social"}


class TestMigrateV2ToV3:
    """Tests for v2 -> v3 migration."""

    def test_migrate_v2_to_v3_adds_encounter_state(self):
        v2_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 2,
            "state": {
                "simulation_state": {
                    "player_state": {
                        "health": 100,
                    },
                }
            },
        }
        result = migrate_v2_to_v3(v2_package)
        player_state = result["state"]["simulation_state"]["player_state"]
        assert "encounter_state" in player_state
        assert "dialogue_state" in player_state
        assert result["schema_version"] == 3

    def test_migrate_v2_to_v3_adds_sandbox_state(self):
        v2_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 2,
            "state": {
                "simulation_state": {}
            },
        }
        result = migrate_v2_to_v3(v2_package)
        sim_state = result["state"]["simulation_state"]
        assert "sandbox_state" in sim_state

    def test_migrate_v2_to_v3_adds_artifacts(self):
        v2_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 2,
            "state": {"simulation_state": {}},
        }
        result = migrate_v2_to_v3(v2_package)
        assert "artifacts" in result
        assert result["artifacts"]["snapshots"] == []
        assert result["artifacts"]["timeline"] == {}

    def test_migrate_v2_to_v3_preserves_player_data(self):
        v2_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 2,
            "state": {
                "simulation_state": {
                    "player_state": {
                        "health": 100,
                        "name": "Hero",
                    },
                }
            },
        }
        result = migrate_v2_to_v3(v2_package)
        player_state = result["state"]["simulation_state"]["player_state"]
        assert player_state["health"] == 100
        assert player_state["name"] == "Hero"


class TestMigrationManager:
    """Tests for the migration manager."""

    def test_migrate_v1_to_current(self):
        v1_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "world": "test_world",
                }
            },
        }
        result = migrate_package_to_current(v1_package)
        assert result["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        sim_state = result["state"]["simulation_state"]
        assert "player_state" in sim_state
        assert "sandbox_state" in sim_state

    def test_migrate_v2_to_current(self):
        v2_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": 2,
            "state": {
                "simulation_state": {
                    "player_state": {"health": 100},
                }
            },
        }
        result = migrate_package_to_current(v2_package)
        assert result["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        player_state = result["state"]["simulation_state"]["player_state"]
        assert "encounter_state" in player_state

    def test_already_at_current_version(self):
        current_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": CURRENT_RPG_SCHEMA_VERSION,
            "state": {
                "simulation_state": {
                    "world": "test_world",
                }
            },
        }
        result = migrate_package_to_current(current_package)
        assert result["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        assert result["state"]["simulation_state"]["world"] == "test_world"

    def test_migrate_package_to_current_handles_none(self):
        result = migrate_package_to_current(None)
        assert isinstance(result, dict)


class TestValidateSavePackage:
    """Tests for package validation."""

    def test_valid_package(self):
        valid_package = {
            "package_type": PACKAGE_TYPE,
            "schema_version": CURRENT_RPG_SCHEMA_VERSION,
            "adventure": {
                "setup_payload": {"world": "test"},
                "metadata": {},
            },
            "state": {
                "simulation_state": {"world": "test"},
            },
        }
        errors = validate_save_package(valid_package)
        assert errors == []

    def test_invalid_package_type(self):
        invalid_package = {
            "package_type": "wrong_type",
            "adventure": {"setup_payload": {}},
            "state": {"simulation_state": {}},
        }
        errors = validate_save_package(invalid_package)
        assert any(e["field"] == "package_type" for e in errors)

    def test_missing_setup_payload(self):
        invalid_package = {
            "package_type": PACKAGE_TYPE,
            "adventure": {"metadata": {}},
            "state": {"simulation_state": {}},
        }
        errors = validate_save_package(invalid_package)
        assert any("setup_payload" in e["field"] for e in errors)

    def test_missing_simulation_state(self):
        invalid_package = {
            "package_type": PACKAGE_TYPE,
            "adventure": {"setup_payload": {}},
            "state": {},
        }
        errors = validate_save_package(invalid_package)
        assert any("simulation_state" in e["field"] for e in errors)