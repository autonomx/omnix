"""Phase 6.5 — Recovery Models: Unit tests.

Tests RecoveryRecord, RecoveryResult, and RecoveryState serialization
round-trips and state tracking.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.recovery.models import (
    RecoveryRecord,
    RecoveryResult,
    RecoveryState,
)


class TestRecoveryRecordRoundtrip:
    def test_recovery_record_roundtrip(self):
        record = RecoveryRecord(
            recovery_id="abc123",
            reason="parser_failure",
            tick=5,
            scene_anchor_id="anchor_1",
            summary="Parser failed",
            selected_policy="fallback_scene",
            metadata={"error": "bad input"},
        )
        data = record.to_dict()
        restored = RecoveryRecord.from_dict(data)

        assert restored.recovery_id == "abc123"
        assert restored.reason == "parser_failure"
        assert restored.tick == 5
        assert restored.scene_anchor_id == "anchor_1"
        assert restored.summary == "Parser failed"
        assert restored.selected_policy == "fallback_scene"
        assert restored.metadata == {"error": "bad input"}


class TestRecoveryResultRoundtrip:
    def test_recovery_result_roundtrip(self):
        record = RecoveryRecord(
            recovery_id="rec1",
            reason="director_failure",
            tick=10,
            summary="Director failed",
            selected_policy="fallback_scene",
        )
        result = RecoveryResult(
            reason="director_failure",
            policy="fallback_scene",
            scene={"title": "Safe scene", "body": "All is well."},
            record=record,
            used_anchor=True,
            used_coherence_summary=False,
        )
        data = result.to_dict()
        restored = RecoveryResult.from_dict(data)

        assert restored.reason == "director_failure"
        assert restored.policy == "fallback_scene"
        assert restored.scene["title"] == "Safe scene"
        assert restored.record is not None
        assert restored.record.recovery_id == "rec1"
        assert restored.used_anchor is True
        assert restored.used_coherence_summary is False


class TestRecoveryStateRoundtrip:
    def test_recovery_state_roundtrip(self):
        state = RecoveryState(
            last_good_scene_anchor={"anchor_id": "a1", "location": "market"},
            recent_recoveries=[
                RecoveryRecord(recovery_id="r1", reason="parser_failure", tick=1),
                RecoveryRecord(recovery_id="r2", reason="contradiction", tick=3),
            ],
            recovery_count_by_scene={"a1": 2},
            last_recovery_reason="contradiction",
            last_recovery_tick=3,
        )
        data = state.to_dict()
        restored = RecoveryState.from_dict(data)

        assert restored.last_good_scene_anchor == {"anchor_id": "a1", "location": "market"}
        assert len(restored.recent_recoveries) == 2
        assert restored.recent_recoveries[0].recovery_id == "r1"
        assert restored.recovery_count_by_scene == {"a1": 2}
        assert restored.last_recovery_reason == "contradiction"
        assert restored.last_recovery_tick == 3


class TestRecoveryStateTracking:
    def test_recovery_state_tracks_last_good_anchor(self):
        state = RecoveryState()
        assert state.last_good_scene_anchor is None
        state.last_good_scene_anchor = {"anchor_id": "a2", "location": "tavern"}
        assert state.last_good_scene_anchor["location"] == "tavern"

    def test_recovery_state_tracks_last_recovery_reason(self):
        state = RecoveryState()
        assert state.last_recovery_reason is None
        state.last_recovery_reason = "renderer_failure"
        assert state.last_recovery_reason == "renderer_failure"
