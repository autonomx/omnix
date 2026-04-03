"""Phase 6.5 - Recovery Manager: Unit tests.

Tests the RecoveryManager handler methods, state tracking,
and serialization round-trips.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.recovery.manager import RecoveryManager
from app.rpg.recovery.models import RecoveryResult, RecoveryState


def _coherence_summary(location="market"):
    return {
        "scene_summary": {"location": location},
        "active_tensions": [{"text": "bandits nearby"}],
        "unresolved_threads": [],
        "recent_consequences": [],
        "last_good_anchor": None,
        "contradictions": [],
    }


class TestRecoveryManagerHandlers:
    def test_handle_parser_failure_returns_recovery_result(self):
        mgr = RecoveryManager()
        result = mgr.handle_parser_failure(
            player_input="garbled input",
            error=ValueError("bad parse"),
            coherence_summary=_coherence_summary(),
            tick=1,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "parser_failure"
        assert result.scene.get("title")
        assert result.record is not None

    def test_handle_director_failure_returns_recovery_result(self):
        mgr = RecoveryManager()
        result = mgr.handle_director_failure(
            player_input="look around",
            error="timeout",
            coherence_summary=_coherence_summary(),
            tick=2,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "director_failure"
        assert result.scene.get("title")

    def test_handle_renderer_failure_returns_recovery_result(self):
        mgr = RecoveryManager()
        result = mgr.handle_renderer_failure(
            player_input="attack",
            error=RuntimeError("render crash"),
            coherence_summary=_coherence_summary(),
            tick=3,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "renderer_failure"
        assert result.scene.get("title")

    def test_handle_contradiction_returns_recovery_result(self):
        mgr = RecoveryManager()
        contradictions = [
            {"message": "Guard alive and dead", "severity": "high"},
        ]
        result = mgr.handle_contradiction(
            contradictions=contradictions,
            coherence_summary=_coherence_summary(),
            tick=4,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "contradiction"
        assert result.scene.get("title")

    def test_handle_ambiguity_auto_resolve_returns_recovery_result(self):
        mgr = RecoveryManager()
        result = mgr.handle_ambiguity(
            player_input="attack",
            parser_result={"confidence": 0.95},
            coherence_summary=_coherence_summary(),
            tick=5,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "ambiguity"
        assert result.policy == "auto_resolve"

    def test_handle_ambiguity_clarification_returns_recovery_result(self):
        mgr = RecoveryManager()
        result = mgr.handle_ambiguity(
            player_input="what do I do here?",
            parser_result={"confidence": 0.1},
            coherence_summary=_coherence_summary(),
            tick=6,
        )
        assert isinstance(result, RecoveryResult)
        assert result.reason == "ambiguity"
        assert result.policy == "request_clarification"


class TestRecoveryManagerState:
    def test_record_last_good_anchor_updates_state(self):
        mgr = RecoveryManager()
        assert mgr._state.last_good_scene_anchor is None
        mgr.record_last_good_anchor({"anchor_id": "a1", "location": "tavern"})
        assert mgr._state.last_good_scene_anchor["anchor_id"] == "a1"

    def test_record_recovery_updates_recent_recoveries(self):
        mgr = RecoveryManager()
        result = mgr.handle_parser_failure(
            player_input="test",
            error="fail",
            coherence_summary=_coherence_summary(),
            tick=1,
        )
        assert len(mgr._state.recent_recoveries) == 1
        assert mgr._state.last_recovery_reason == "parser_failure"
        assert mgr._state.last_recovery_tick == 1

    def test_high_severity_contradiction_detection(self):
        mgr = RecoveryManager()
        assert mgr._has_high_severity_contradiction([
            {"severity": "high", "message": "conflict"},
        ]) is True
        assert mgr._has_high_severity_contradiction([
            {"severity": "low", "message": "minor"},
        ]) is False
        assert mgr._has_high_severity_contradiction([
            {"severity": "critical", "message": "major"},
        ]) is True
        assert mgr._has_high_severity_contradiction([]) is False


class TestRecoveryManagerSerialization:
    def test_serialize_deserialize_roundtrip_preserves_recovery_state(self):
        mgr = RecoveryManager()
        mgr.record_last_good_anchor({"anchor_id": "a1", "location": "market"})
        mgr.handle_parser_failure(
            player_input="test",
            error="fail",
            coherence_summary=_coherence_summary(),
            tick=1,
        )
        mgr.handle_director_failure(
            player_input="look",
            error="timeout",
            coherence_summary=_coherence_summary(),
            tick=2,
        )

        data = mgr.serialize_state()
        mgr2 = RecoveryManager()
        mgr2.deserialize_state(data)

        assert mgr2._state.last_good_scene_anchor["anchor_id"] == "a1"
        assert len(mgr2._state.recent_recoveries) == 2
        assert mgr2._state.last_recovery_reason == "director_failure"
        assert mgr2._state.last_recovery_tick == 2
