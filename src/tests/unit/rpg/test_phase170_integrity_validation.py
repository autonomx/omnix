"""Phase 17.0 — Integrity validation unit tests."""
import pytest

from app.rpg.validation.integrity import (
    assert_package_integrity,
    assert_session_integrity,
    validate_memory_state,
    validate_package_integrity,
    validate_session_integrity,
    validate_simulation_state,
    validate_visual_state,
)


class TestVisualStateValidation:
    """Tests for visual state validation."""

    def test_validate_visual_state_valid(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "pending"},
                        {"request_id": "r2", "status": "complete"},
                    ],
                    "visual_assets": [
                        {"asset_id": "a1", "status": "complete", "created_from_request_id": "r2"},
                    ],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is True
        assert len(result["errors"]) == 0

    def test_validate_visual_state_rejects_duplicate_request_ids(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "pending"},
                        {"request_id": "r1", "status": "pending"},
                    ],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_request_duplicate_id" for e in result["errors"])

    def test_validate_visual_state_rejects_duplicate_asset_ids(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [],
                    "visual_assets": [
                        {"asset_id": "a1", "status": "complete"},
                        {"asset_id": "a1", "status": "complete"},
                    ],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_asset_duplicate_id" for e in result["errors"])

    def test_validate_visual_state_rejects_invalid_status(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "r1", "status": "invalid_status"},
                    ],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_request_invalid_status" for e in result["errors"])

    def test_validate_visual_state_missing_request_id(self):
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {"request_id": "", "status": "pending"},
                    ],
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_request_missing_id" for e in result["errors"])

    def test_validate_visual_state_over_cap(self):
        image_requests = [{"request_id": f"r{i}", "status": "pending"} for i in range(101)]
        simulation_state = {
            "presentation_state": {
                "visual_state": {
                    "image_requests": image_requests,
                    "visual_assets": [],
                }
            }
        }
        result = validate_visual_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "visual_requests_over_cap" for e in result["errors"])


class TestMemoryStateValidation:
    """Tests for memory state validation."""

    def test_validate_memory_state_valid(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "fact", "strength": 0.5}]},
                },
                "world_memory": {"rumors": [{"text": "rumor", "strength": 0.3, "reach": 1}]},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is True

    def test_validate_memory_state_rejects_strength_out_of_bounds(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "fact", "strength": 2.0}]}
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "actor_memory_strength_out_of_bounds" for e in result["errors"])

    def test_validate_memory_state_rejects_missing_text(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "", "strength": 0.5}]}
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "actor_memory_missing_text" for e in result["errors"])

    def test_validate_memory_state_negative_strength(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "fact", "strength": -0.5}]}
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "actor_memory_strength_out_of_bounds" for e in result["errors"])

    def test_validate_memory_state_rumor_strength_out_of_bounds(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {},
                "world_memory": {"rumors": [{"text": "rumor", "strength": 1.5, "reach": 1}]},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "world_rumor_strength_out_of_bounds" for e in result["errors"])

    def test_validate_memory_state_negative_reach(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {},
                "world_memory": {"rumors": [{"text": "rumor", "strength": 0.5, "reach": -1}]},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "world_rumor_negative_reach" for e in result["errors"])

    def test_validate_memory_state_invalid_strength_type_does_not_crash(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {
                    "npc:a": {"entries": [{"text": "fact", "strength": {"bad": "type"}}]}
                },
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "actor_memory_invalid_strength_type" for e in result["errors"])

    def test_validate_memory_state_invalid_rumor_types_do_not_crash(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {},
                "world_memory": {
                    "rumors": [
                        {"text": "rumor", "strength": {"bad": 1}, "reach": {"bad": 2}}
                    ]
                },
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "world_rumor_invalid_strength_type" for e in result["errors"])
        assert any(e["code"] == "world_rumor_invalid_reach_type" for e in result["errors"])

    def test_validate_memory_state_actor_memory_over_cap(self):
        entries = [{"text": f"fact{i}", "strength": 0.5} for i in range(51)]
        simulation_state = {
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": entries}},
                "world_memory": {"rumors": []},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "actor_memory_over_cap" for e in result["errors"])

    def test_validate_memory_state_world_rumors_over_cap(self):
        rumors = [{"text": f"rumor{i}", "strength": 0.5, "reach": 1} for i in range(51)]
        simulation_state = {
            "memory_state": {
                "actor_memory": {},
                "world_memory": {"rumors": rumors},
            }
        }
        result = validate_memory_state(simulation_state)
        assert result["ok"] is False
        assert any(e["code"] == "world_rumors_over_cap" for e in result["errors"])


class TestSessionIntegrityValidation:
    """Tests for session integrity validation."""

    def test_validate_session_integrity_requires_manifest_id(self):
        session = {"manifest": {}, "simulation_state": {}}
        result = validate_session_integrity(session)
        assert result["ok"] is False
        assert any(e["code"] == "manifest_missing_id" for e in result["errors"])

    def test_validate_session_integrity_requires_schema_version(self):
        session = {"manifest": {"id": "s1", "schema_version": 0}, "simulation_state": {}}
        result = validate_session_integrity(session)
        assert result["ok"] is False
        assert any(e["code"] == "manifest_invalid_schema_version" for e in result["errors"])

    def test_validate_session_integrity_valid(self):
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


class TestPackageIntegrityValidation:
    """Tests for package integrity validation."""

    def test_validate_package_integrity_checks_session_like_structure(self):
        package_payload = {
            "session_manifest": {"id": "s1", "schema_version": 2},
            "simulation_state": {
                "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
                "presentation_state": {"visual_state": {"image_requests": [], "visual_assets": []}},
            },
        }
        result = validate_package_integrity(package_payload)
        assert result["ok"] is True

    def test_validate_package_integrity_invalid_memory(self):
        package_payload = {
            "session_manifest": {"id": "s1", "schema_version": 2},
            "simulation_state": {
                "memory_state": {
                    "actor_memory": {
                        "npc:a": {"entries": [{"text": "fact", "strength": 99.0}]}
                    },
                    "world_memory": {"rumors": []},
                },
                "presentation_state": {
                    "visual_state": {"image_requests": [], "visual_assets": []},
                },
            },
        }
        result = validate_package_integrity(package_payload)
        assert result["ok"] is False


class TestSimulationStateValidation:
    """Tests for simulation-state aggregation."""

    def test_validate_simulation_state_aggregates_visual_and_memory_errors(self):
        simulation_state = {
            "memory_state": {
                "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 9.0}]}},
                "world_memory": {"rumors": []},
            },
            "presentation_state": {
                "visual_state": {
                    "image_requests": [{"request_id": "r1", "status": "bad_status"}],
                    "visual_assets": [],
                }
            },
        }
        result = validate_simulation_state(simulation_state)
        assert result["ok"] is False
        assert len(result["errors"]) >= 2


class TestAssertFunctions:
    """Tests for assert functions that raise exceptions."""

    def test_assert_session_integrity_raises_on_invalid(self):
        session = {"manifest": {}, "simulation_state": {}}
        with pytest.raises(ValueError):
            assert_session_integrity(session)

    def test_assert_package_integrity_raises_on_invalid(self):
        package_payload = {
            "session_manifest": {"id": "s1", "schema_version": 2},
            "simulation_state": {
                "memory_state": {
                    "actor_memory": {
                        "npc:a": {"entries": [{"text": "fact", "strength": 99.0}]}
                    },
                    "world_memory": {"rumors": []},
                },
                "presentation_state": {
                    "visual_state": {"image_requests": [], "visual_assets": []},
                },
            },
        }
        with pytest.raises(ValueError):
            assert_package_integrity(package_payload)

    def test_assert_session_integrity_passes_on_valid(self):
        session = {
            "manifest": {"id": "s1", "schema_version": 2},
            "simulation_state": {
                "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
                "presentation_state": {
                    "visual_state": {"image_requests": [], "visual_assets": []},
                },
            },
        }
        result = assert_session_integrity(session)
        assert result["ok"] is True