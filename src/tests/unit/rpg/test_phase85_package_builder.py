"""Unit tests for Phase 8.5 package builder and loader."""
import pytest

from app.rpg.persistence.package_builder import build_save_package
from app.rpg.persistence.package_loader import load_save_package
from app.rpg.persistence.save_schema import (
    CURRENT_RPG_SCHEMA_VERSION,
    PACKAGE_TYPE,
    ENGINE_VERSION,
)


class TestBuildSavePackage:
    """Tests for build_save_package."""

    def test_build_package_has_required_keys(self):
        setup_payload = {
            "world": "test_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                }
            }
        }
        package = build_save_package(setup_payload)
        assert package["package_type"] == PACKAGE_TYPE
        assert package["schema_version"] == CURRENT_RPG_SCHEMA_VERSION
        assert package["engine_version"] == ENGINE_VERSION
        assert "created_at" in package
        assert "updated_at" in package

    def test_build_package_includes_setup_payload(self):
        setup_payload = {
            "world": "test_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                }
            }
        }
        package = build_save_package(setup_payload)
        assert package["adventure"]["setup_payload"] == setup_payload

    def test_build_package_includes_simulation_state(self):
        setup_payload = {
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                    "tick": 42,
                }
            }
        }
        package = build_save_package(setup_payload)
        assert package["state"]["simulation_state"]["players"] == ["hero"]
        assert package["state"]["simulation_state"]["tick"] == 42

    def test_build_package_includes_artifacts(self):
        setup_payload = {
            "metadata": {
                "simulation_state": {
                    "snapshots": ["snap1", "snap2"],
                    "timeline": {"events": []},
                }
            }
        }
        package = build_save_package(setup_payload)
        assert package["artifacts"]["snapshots"] == ["snap1", "snap2"]
        assert package["artifacts"]["timeline"] == {"events": []}

    def test_build_package_handles_none_input(self):
        package = build_save_package(None)
        assert package["package_type"] == PACKAGE_TYPE
        assert package["schema_version"] == CURRENT_RPG_SCHEMA_VERSION

    def test_build_package_handles_empty_metadata(self):
        setup_payload = {}
        package = build_save_package(setup_payload)
        assert package["adventure"]["setup_payload"] == {}
        assert package["state"]["simulation_state"] == {}


class TestLoadSavePackage:
    """Tests for load_save_package."""

    def test_load_package_returns_setup_payload(self):
        setup_payload = {
            "world": "test_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                }
            }
        }
        package = build_save_package(setup_payload)
        result = load_save_package(package)
        assert isinstance(result, dict)
        assert "metadata" in result

    def test_load_package_reconstructs_simulation_state(self):
        setup_payload = {
            "metadata": {
                "simulation_state": {
                    "players": ["hero"],
                    "tick": 42,
                }
            }
        }
        package = build_save_package(setup_payload)
        result = load_save_package(package)
        assert result["metadata"]["simulation_state"]["players"] == ["hero"]
        assert result["metadata"]["simulation_state"]["tick"] == 42

    def test_load_package_raises_on_invalid(self):
        invalid_package = {
            "package_type": "wrong",
            "adventure": {"setup_payload": {}},
            "state": {"simulation_state": {}},
        }
        with pytest.raises(ValueError):
            load_save_package(invalid_package)

    def test_load_package_with_v1_package(self):
        v1_package = {
            "package_type": "rpg_save_package",
            "schema_version": 1,
            "adventure": {
                "setup_payload": {"metadata": {}},
            },
            "state": {
                "simulation_state": {
                    "world": "test",
                }
            },
        }
        result = load_save_package(v1_package)
        assert result["metadata"]["simulation_state"]["world"] == "test"
        assert "player_state" in result["metadata"]["simulation_state"]


class TestRoundTrip:
    """Tests for export -> import roundtrip."""

    def test_roundtrip_preserves_data(self):
        original_setup = {
            "world": "test_world",
            "metadata": {
                "simulation_state": {
                    "players": ["hero", "villain"],
                    "tick": 100,
                    "snapshots": ["snap1"],
                    "timeline": {"key_events": [1, 2, 3]},
                }
            }
        }
        package = build_save_package(original_setup)
        result = load_save_package(package)
        assert result["metadata"]["simulation_state"]["players"] == ["hero", "villain"]
        assert result["metadata"]["simulation_state"]["tick"] == 100
        assert result["metadata"]["simulation_state"]["snapshots"] == ["snap1"]
        assert result["metadata"]["simulation_state"]["timeline"] == {"key_events": [1, 2, 3]}