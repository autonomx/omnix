"""Phase 17.0 — Integrity validation functional tests."""
import pytest

from app.rpg.validation.integrity import (
    validate_visual_state,
    validate_memory_state,
    validate_session_integrity,
    validate_package_integrity,
    validate_simulation_state,
    assert_session_integrity,
    assert_package_integrity,
)


class TestVisualStateFunctional:
    """Functional tests for visual state validation."""

    def test_accepts_valid_state_with_linked_assets(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "complete"},
                        {"request_id": "r2", "status": "pending"},
                    ],
                    "visual_assets": [
                        {
                            "asset_id": "a1",
                            "status": "complete",
                            "created_from_request_id": "r1",
                        },
                        {
                            "asset_id": "a2",
                            "status": "pending",
                            "created_from_request_id": "r2",
                        },
                    ],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is True
        assert len(result["warnings"]) == 0

    def test_warns_on_missing_request_reference(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "complete"},
                    ],
                    "visual_assets": [
                        {
                            "asset_id": "a1",
                            "status": "complete",
                            "created_from_request_id": "r_missing",
                        },
                    ],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is True
        assert len(result["warnings"]) > 0
        assert "visual_asset_request_reference_missing" in result["warnings"][0]["code"]


class TestMemoryStateFunctional:
    """Functional tests for memory state validation."""

    def test_accepts_valid_complex_memory(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {
                        "entries": [
                            {"text": "fact 1", "strength": 0.5},
                            {"text": "fact 2", "strength": 0.3},
                        ]
                    },
                    "npc:b": {
                        "entries": [
                            {"text": "secret", "strength": 1.0},
                        ]
                    },
                },
                "world_memory": {
                    "rumors": [
                        {"text": "rumor 1", "strength": 0.2, "reach": 1},
                        {"text": "rumor 2", "strength": 0.8, "reach": 5},
                    ]
                },
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is True

    def test_empty_state_is_valid(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {},
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is True


class TestSessionIntegrityFunctional:
    """Functional tests for session integrity validation."""

    def test_complete_valid_session(self):
        session = {
            "manifest": {"id": "s1", "schema_version": 2},
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
        result = validate_session_integrity(session)
        assert result["ok"] is True

    def test_counts_returned_in_result(self):
        session = {
            "manifest": {"id": "s1", "schema_version": 2},
            "simulation_state": {
                "memory_state": {
                    "actor_memory": {
                        "npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}
                    },
                    "world_memory": {"rumors": [{"text": "rumor", "strength": 0.5, "reach": 1}]},
                },
                "presentation_state": {
                    "visual_state": {
                        "image_requests": [{"request_id": "r1", "status": "pending"}],
                        "visual_assets": [{"asset_id": "a1", "status": "complete", "created_from_request_id": "r1"}],
                    }
                },
            },
        }
        result = validate_session_integrity(session)
        assert result["ok"] is True
        assert result["counts"]["memory_actors"] == 1
        assert result["counts"]["memory_rumors"] == 1
        assert result["counts"]["visual_requests"] == 1
        assert result["counts"]["visual_assets"] == 1


class TestPackageIntegrityFunctional:
    """Functional tests for package integrity validation."""

    def test_valid_package_with_complete_state(self):
        package_payload = {
            "session_manifest": {"id": "s1", "schema_version": 2},
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

    def test_invalid_package_blocks_import(self):
        package_payload = {
            "session_manifest": {},
            "simulation_state": {
                "memory_state": {
                    "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": -1}]}},
                    "world_memory": {"rumors": []},
                },
                "presentation_state": {
                    "visual_state": {"image_requests": [], "visual_assets": []},
                },
            },
        }
        with pytest.raises(ValueError):
            assert_package_integrity(package_payload)


class TestSimulationStateFunctional:
    """Functional tests for simulation state validation."""

    def test_complete_valid_simulation(self):
        simulation_state = {
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
        }
        result = validate_simulation_state(simulation_state)
        assert result["ok"] is True

    def test_simulation_state_reports_combined_counts(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}},
                "world_memory": {"rumors": [{"text": "rumor", "strength": 0.5, "reach": 1}]},
            },
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "r1", "status": "pending"}],
                    "visual_assets": [{"asset_id": "a1", "status": "complete", "created_from_request_id": "r1"}],
                }
            },
        }
        result = validate_simulation_state(simulation_state)
        assert result["ok"] is True
        assert result["counts"]["visual_requests"] == 1
        assert result["counts"]["visual_assets"] == 1
        assert result["counts"]["memory_actors"] == 1
        assert result["counts"]["memory_rumors"] == 1

    def test_combined_errors_from_visual_and_memory(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {"a": {"entries": [{"text": "f", "strength": 2.0}]}},
                "world_memory": {"rumors": []},
            },
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "unknown"},
                        {"request_id": "r1", "status": "unknown"},
                    ],
                    "visual_assets": [],
                }
            },
        }
        result = validate_simulation_state(simulation_state)
        assert result["ok"] is False
        codes = [e["code"] for e in result["errors"]]
        assert "actor_memory_strength_out_of_bounds" in codes
        assert "visual_request_duplicate_id" in codes
        assert "visual_request_invalid_status" in codes