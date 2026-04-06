"""Phase 19 — GM Tools Follow-up Regression Tests.

Tests for world_data JSON validation during import.
"""

from app.rpg.creator.gm_tools import ContentPackager


class TestPhase19GMToolsFollowupRegression:
    """Regression tests for Phase 19 GM tools follow-up fixes."""

    def test_phase19_import_state_rejects_non_json_like_world_data(self):
        """Verify import_state rejects non-JSON-like world_data."""
        package = {
            "_format_version": 1,
            "gm_state": {"gm_id": "gm1"},
            "world_data": {"bad": set([1, 2, 3])},
        }
        out = ContentPackager.import_state(package)
        assert out["success"] is False
        assert out["reason"] == "invalid world_data payload"