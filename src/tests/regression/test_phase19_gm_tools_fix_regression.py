"""Phase 19 — GM Tools Fix Regression Tests.

Tests for override validation, package import safety,
and GM state normalization.
"""

from app.rpg.creator.gm_tools import (
    ContentPackager,
    GMDeterminismValidator,
    GMState,
    RuntimeOverrideTools,
)


class TestPhase19GMToolsFixRegression:
    """Regression tests for Phase 19 GM tools fixes."""

    def test_phase19_add_override_rejects_invalid_type_and_dedupes(self):
        """Verify add_override rejects invalid type and dedupes by key."""
        gm_state = GMState()
        bad = RuntimeOverrideTools.add_override(
            gm_state,
            {"type": "invalid", "target_id": "npc:1", "payload": {}},
            tick=1,
        )
        assert bad["success"] is False

        ok1 = RuntimeOverrideTools.add_override(
            gm_state,
            {"type": "pause_actor", "target_id": "npc:1", "payload": {"paused": True}},
            tick=1,
        )
        ok2 = RuntimeOverrideTools.add_override(
            gm_state,
            {"type": "pause_actor", "target_id": "npc:1", "payload": {"paused": False}},
            tick=2,
        )
        assert ok1["success"] is True
        assert ok2["success"] is True
        assert len(gm_state.active_overrides) == 1
        assert gm_state.active_overrides[0]["tick"] == 2

    def test_phase19_import_state_rejects_invalid_package_and_normalizes_valid_one(self):
        """Verify import_state rejects invalid packages and normalizes valid ones."""
        bad = ContentPackager.import_state({"_format_version": 99})
        assert bad["success"] is False

        good = ContentPackager.import_state({
            "_format_version": 1,
            "gm_state": {
                "gm_id": "gm1",
                "active_overrides": [
                    {"type": "pause_actor", "target_id": "npc:1", "payload": {}, "tick": 1},
                    {"type": "invalid", "target_id": "npc:2", "payload": {}, "tick": 1},
                ],
            },
            "world_data": {"scene_id": "scene:test"},
        })
        assert good["success"] is True
        normalized = good["gm_state"]
        assert len(normalized["active_overrides"]) == 1
        assert normalized["active_overrides"][0]["type"] == "pause_actor"

    def test_phase19_normalize_state_sorts_and_filters_overrides(self):
        """Verify normalize_state sorts and filters overrides."""
        gm_state = GMState(
            active_overrides=[
                {"type": "pause_actor", "target_id": "b", "payload": {}, "tick": 1},
                {"type": "invalid", "target_id": "a", "payload": {}, "tick": 1},
                {"type": "pause_actor", "target_id": "a", "payload": {}, "tick": 1},
            ]
        )
        out = GMDeterminismValidator.normalize_state(gm_state)
        assert [v["target_id"] for v in out.active_overrides] == ["a", "b"]

    def test_phase19_validate_bounds_catches_invalid_override_type(self):
        """Verify validate_bounds catches invalid override types."""
        gm_state = GMState(
            active_overrides=[
                {"type": "invalid_type", "target_id": "npc:1", "payload": {}, "tick": 1},
            ]
        )
        violations = GMDeterminismValidator.validate_bounds(gm_state)
        assert any("invalid override type" in v for v in violations)

    def test_phase19_validate_bounds_catches_missing_target_id(self):
        """Verify validate_bounds catches override missing target_id."""
        gm_state = GMState(
            active_overrides=[
                {"type": "pause_actor", "target_id": "", "payload": {}, "tick": 1},
            ]
        )
        violations = GMDeterminismValidator.validate_bounds(gm_state)
        assert any("missing target_id" in v for v in violations)

    def test_phase19_add_override_rejects_missing_target_id(self):
        """Verify add_override rejects override with missing target_id."""
        gm_state = GMState()
        result = RuntimeOverrideTools.add_override(
            gm_state,
            {"type": "pause_actor", "target_id": "", "payload": {}},
            tick=1,
        )
        assert result["success"] is False
        assert "missing target_id" in result.get("reason", "")

    def test_phase19_import_state_validates_format_version(self):
        """Verify import_state validates format version."""
        bad = ContentPackager.import_state({"_format_version": 2, "gm_state": {}, "world_data": {}})
        assert bad["success"] is False

    def test_phase19_import_state_validates_required_keys(self):
        """Verify import_state validates required keys."""
        bad = ContentPackager.import_state({
            "_format_version": 1,
            "gm_state": {},
        })
        assert bad["success"] is False

    def test_phase19_export_state_returns_normalized_data(self):
        """Verify export_state returns normalized GM state."""
        gm_state = GMState(
            active_overrides=[
                {"type": "invalid", "target_id": "npc:1", "payload": {}, "tick": 1},
                {"type": "pause_actor", "target_id": "npc:2", "payload": {}, "tick": 1},
            ]
        )
        result = ContentPackager.export_state(gm_state, {"scene_id": "s1"})
        assert result["success"] is True
        package = result["package"]
        assert len(package["gm_state"]["active_overrides"]) == 1
        assert package["gm_state"]["active_overrides"][0]["type"] == "pause_actor"

    def test_phase19_normalize_state_filters_edit_history(self):
        """Verify normalize_state filters non-dict items from edit_history."""
        gm_state = GMState(
            edit_history=[
                {"type": "edit_npc", "npc_id": "npc:1", "tick": 1},
                "not_a_dict",
                42,
                None,
            ]
        )
        out = GMDeterminismValidator.normalize_state(gm_state)
        assert len(out.edit_history) == 1
        assert out.edit_history[0]["type"] == "edit_npc"