"""Phase 17.0 — Integrity validation regression tests.

This module ensures that future changes don't break the integrity
validation guarantees established in Phase 17.0.
"""
import pytest

from app.rpg.validation.integrity import (
    validate_visual_state,
    validate_memory_state,
    validate_session_integrity,
    validate_package_integrity,
    validate_simulation_state,
)


class TestVisualStateRegression:
    """Regression tests for visual state validation."""

    def test_visual_state_accepts_empty_state(self):
        """Regression: empty visual state should be valid."""
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is True

    def test_visual_state_accepts_default_status(self):
        """Regression: pending/complete/failed/blocked are valid."""
        for status in {"pending", "complete", "failed", "blocked"}:
            simulation_state = {
                "presentation_state": {
                    "visual_state": {
                        "image_requests": [{"request_id": "r1", "status": status}],
                        "visual_assets": [],
                    }
                }
            }
            result = validate_visual_state(simulation_state)
            assert result["ok"] is True, f"Failed for status: {status}"

    def test_visual_state_rejects_arbitrary_status(self):
        """Regression: invalid status should be rejected."""
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "r1", "status": "arbitrary"}],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_request_invalid_status" for e in result["errors"])

    def test_visual_state_rejects_null_request_id(self):
        """Regression: null request_id should be rejected."""
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": None, "status": "pending"}],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_request_missing_id" for e in result["errors"])


class TestMemoryStateRegression:
    """Regression tests for memory state validation."""

    def test_memory_state_accepts_boundary_values(self):
        """Regression: strength=0.0 and strength=1.0 are valid."""
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {
                        "entries": [
                            {"text": "zero", "strength": 0.0},
                            {"text": "one", "strength": 1.0},
                        ]
                    }
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is True

    def test_memory_state_rejects_epsilon_above_one(self):
        """Regression: strength > 1.0 must be rejected."""
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "fact", "strength": 1.001}]}
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False


class TestSessionIntegrityRegression:
    """Regression tests for session integrity validation."""

    def test_session_rejects_negative_schema(self):
        """Regression: negative schema_version must be rejected."""
        session = {"manifest": {"id": "s1", "schema_version": -1}, "simulation_state": {}}
        result = validate_session_integrity(session)
        assert result["ok"] is False
        assert any(e["code"] == "manifest_invalid_schema_version" for e in result["errors"])

    def test_session_rejects_whitespace_id(self):
        """Regression: whitespace-only session id must be rejected."""
        session = {"manifest": {"id": "   ", "schema_version": 1}, "simulation_state": {}}
        result = validate_session_integrity(session)
        assert result["ok"] is False
        assert any(e["code"] == "manifest_missing_id" for e in result["errors"])


class TestPackageIntegrityRegression:
    """Regression tests for package integrity validation."""

    def test_package_accepts_minimal_valid_state(self):
        """Regression: minimal valid package must pass."""
        package_payload = {
            "session_manifest": {"id": "s1", "schema_version": 1},
            "simulation_state": {
                "memory_state": {
                    "actor_memory": {},
                    "world_memory": {"rumors": []},
                },
                "presentation_state": {
                    "visual_state": {
                        "image_requests": [],
                        "visual_assets": [],
                    }
                },
            },
        }
        result = validate_package_integrity(package_payload)
        assert result["ok"] is True


class TestSimulationStateRegression:
    """Regression tests for simulation state validation."""

    def test_simulation_state_handles_nested_missing_keys(self):
        """Regression: nested missing keys should not crash."""
        simulation_state = {}  # Completely empty
        result = validate_simulation_state(simulation_state)
        # Should return valid structure (empty is valid for nested)
        assert isinstance(result["ok"], bool)

    def test_simulation_state_counts_all_elements(self):
        """Regression: all count fields must be present."""
        simulation_state = {
            "memory_state": {
                "actor_memory": {"a": {"entries": []}},
                "world_memory": {"rumors": []},
            },
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": [],
                }
            },
        }
        result = validate_simulation_state(simulation_state)
        assert "visual_requests" in result["counts"]
        assert "visual_assets" in result["counts"]
        assert "memory_actors" in result["counts"]
        assert "memory_rumors" in result["counts"]