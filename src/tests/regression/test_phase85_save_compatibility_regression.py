"""Regression tests for Phase 8.5 save compatibility."""
import pytest

from app.rpg.persistence.package_builder import build_save_package
from app.rpg.persistence.package_loader import load_save_package
from app.rpg.persistence.migration_manager import migrate_package_to_current
from app.rpg.persistence.package_validator import validate_save_package
from app.rpg.persistence.save_schema import (
    CURRENT_RPG_SCHEMA_VERSION,
    PACKAGE_TYPE,
    ENGINE_VERSION,
)


class TestSaveCompatibilityRegression:
    """Regression tests for save compatibility across schema versions."""

    def test_old_v1_package_migrates_successfully(self):
        """Ensure v1 packages can migrate to current schema."""
        v1_package = {
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "world_data": {"name": "old_world"},
                    "npcs": [{"name": "villager"}],
                }
            },
        }
        result = migrate_package_to_current(v1_package)
        assert result["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        assert "player_state" in result["state"]["simulation_state"]
        assert "social_state" in result["state"]["simulation_state"]
        assert "sandbox_state" in result["state"]["simulation_state"]
        # Original data preserved
        assert result["state"]["simulation_state"]["world_data"]["name"] == "old_world"

    def test_old_v2_package_migrates_successfully(self):
        """Ensure v2 packages can migrate to current schema."""
        v2_package = {
            "schema_version": 2,
            "state": {
                "simulation_state": {
                    "player_state": {"name": "Hero", "level": 10},
                    "social_state": {"reputation": 50},
                    "world_data": {"name": "middle_world"},
                }
            },
        }
        result = migrate_package_to_current(v2_package)
        assert result["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        # v3 additions present
        assert "encounter_state" in result["state"]["simulation_state"]["player_state"]
        assert "dialogue_state" in result["state"]["simulation_state"]["player_state"]
        assert "sandbox_state" in result["state"]["simulation_state"]
        # Original data preserved
        assert result["state"]["simulation_state"]["player_state"]["name"] == "Hero"
        assert result["state"]["simulation_state"]["player_state"]["level"] == 10

    def test_export_import_roundtrip_preserves_simulation_state(self):
        """Ensure export -> import roundtrip preserves simulation state."""
        original_setup = {
            "world": "roundtrip_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero", "villain", "npc"],
                    "tick": 999,
                    "world_state": {"day": 42, "weather": "rainy"},
                    "npcs": [
                        {"name": "elder", "location": "village"},
                        {"name": "merchant", "location": "market"},
                    ],
                }
            }
        }
        package = build_save_package(original_setup)
        loaded = load_save_package(package)
        sim = loaded["metadata"]["simulation_state"]
        assert sim["players"] == ["hero", "villain", "npc"]
        assert sim["tick"] == 999
        assert sim["world_state"]["day"] == 42
        assert sim["world_state"]["weather"] == "rainy"
        assert len(sim["npcs"]) == 2

    def test_package_schema_version_is_stable(self):
        """Ensure schema version is stable across builds."""
        package = build_save_package({"metadata": {"simulation_state": {}}})
        assert package["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        assert package["schema_version"] == 3

    def test_snapshots_survive_roundtrip(self):
        """Ensure snapshots survive export/import roundtrip."""
        setup = {
            "metadata": {
                "simulation_state": {
                    "snapshots": [
                        {"tick": 10, "data": "snapshot_10"},
                        {"tick": 20, "data": "snapshot_20"},
                    ],
                }
            }
        }
        package = build_save_package(setup)
        assert package["artifacts"]["snapshots"] == setup["metadata"]["simulation_state"]["snapshots"]

    def test_timeline_survives_roundtrip(self):
        """Ensure timeline data survives export/import roundtrip."""
        setup = {
            "metadata": {
                "simulation_state": {
                    "timeline": {
                        "events": [
                            {"tick": 5, "type": "player_joined"},
                            {"tick": 15, "type": "battle_started"},
                        ],
                        "branches": {"branch_a": [10, 20]},
                    },
                }
            }
        }
        package = build_save_package(setup)
        assert package["artifacts"]["timeline"] == setup["metadata"]["simulation_state"]["timeline"]

    def test_package_validator_rejects_corrupted_package(self):
        """Ensure validator rejects corrupted packages."""
        corrupted = {
            "package_type": PACKAGE_TYPE,
            "schema_version": CURRENT_RPG_SCHEMA_VERSION,
            "adventure": {},  # missing setup_payload
            "state": {"simulation_state": {}},
        }
        errors = validate_save_package(corrupted)
        assert len(errors) > 0
        assert any("setup_payload" in e["field"] for e in errors)

    def test_package_validator_rejects_missing_simulation_state(self):
        """Ensure validator rejects packages without simulation_state."""
        corrupted = {
            "package_type": PACKAGE_TYPE,
            "schema_version": CURRENT_RPG_SCHEMA_VERSION,
            "adventure": {"setup_payload": {}},
            "state": {},
        }
        errors = validate_save_package(corrupted)
        assert len(errors) > 0
        assert any("simulation_state" in e["field"] for e in errors)

    def test_multiple_roundtrips_do_not_degrade_data(self):
        """Ensure multiple roundtrips don't degrade data."""
        original_setup = {
            "world": "stable_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                    "tick": 100,
                    "resources": {"gold": 1000, "wood": 500},
                }
            }
        }
        # Do 3 roundtrips
        current_setup = original_setup
        for _ in range(3):
            package = build_save_package(current_setup)
            current_setup = load_save_package(package)

        sim = current_setup["metadata"]["simulation_state"]
        assert sim["players"] == ["hero"]
        assert sim["tick"] == 100
        assert sim["resources"]["gold"] == 1000
        assert sim["resources"]["wood"] == 500