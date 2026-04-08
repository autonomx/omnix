"""Phase 6.5 - Recovery Manager: Unit tests.

Tests the RecoveryManager handler methods, state tracking,
and serialization round-trips.
"""
import os
import sys

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

    def test_high_severity_contradiction_detection_ignores_warning_only(self):
        """Severity 'warning' and 'info' should NOT trigger high severity detection."""
        mgr = RecoveryManager()
        contradictions = [
            {"severity": "info", "message": "info msg"},
            {"severity": "warning", "message": "warn msg"},
            {"severity": "low", "message": "low msg"},
        ]
        assert mgr._has_high_severity_contradiction(contradictions) is False

    def test_policy_escalation_after_repeated_failures(self):
        """After ESCALATION_THRESHOLD recoveries, policy should escalate to hard_reset_to_anchor."""
        mgr = RecoveryManager()
        mgr.record_last_good_anchor({"anchor_id": "anc1", "location": "dungeon"})
        coherence = {"scene_summary": {"location": "dungeon"}}
        # First recovery: normal policy (count was 0 before call)
        result1 = mgr.handle_parser_failure("input", "err", coherence, tick=1)
        assert result1.policy == "fallback_scene"
        # Second recovery: still normal (count was 1 before call)
        result2 = mgr.handle_parser_failure("input", "err", coherence, tick=2)
        assert result2.policy == "fallback_scene"
        # Third recovery: still normal (count was 2 before call, threshold is 3)
        result3 = mgr.handle_parser_failure("input", "err", coherence, tick=3)
        assert result3.policy == "fallback_scene"
        # Fourth recovery: should escalate (count was 3 before call, 3 >= 3)
        result4 = mgr.handle_parser_failure("input", "err", coherence, tick=4)
        assert "hard_reset" in result4.policy

    def test_recovery_scene_is_tagged_with_metadata(self):
        """All recovery scenes should carry recovered=True and policy fields."""
        mgr = RecoveryManager()
        coherence = {"scene_summary": {"location": "market"}}
        result = mgr.handle_parser_failure("input", "err", coherence, tick=1)
        scene = result.scene
        meta = scene.get("meta", {})
        metadata = scene.get("metadata", {})
        assert meta.get("recovered") is True
        assert meta.get("recovery_reason") == "parser_failure"
        assert meta.get("recovery_policy") is not None
        # Also check backward compat key
        assert metadata.get("recovered") is True

    def test_scene_output_normalization_keys(self):
        """Normalized scenes should have canonical keys: scene, options, meta."""
        mgr = RecoveryManager()
        coherence = {"scene_summary": {"location": "forest"}}
        result = mgr.handle_director_failure("go north", "timeout", coherence, tick=1)
        scene = result.scene
        assert "scene" in scene
        assert "options" in scene
        assert "meta" in scene
        assert "title" in scene


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


def test_tag_recovery_scene_does_not_mutate_input_nested_dicts():
    manager = RecoveryManager()
    original = {
        "scene": "hello",
        "meta": {"existing": True},
        "metadata": {"legacy": True},
        "narrative": {"title": "Hi"},
    }

    tagged = manager._tag_recovery_scene(original, "parser_failure", "fallback_scene")

    assert original["meta"] == {"existing": True}
    assert original["metadata"] == {"legacy": True}
    assert tagged["meta"]["recovered"] is True
    assert tagged["metadata"]["recovered"] is True


def test_select_policy_escalates_on_fourth_recovery_when_threshold_is_three():
    manager = RecoveryManager()
    anchor_id = "anchor:market"
    manager._state.recovery_count_by_scene[anchor_id] = 2
    assert manager._select_policy("fallback_scene", anchor_id) == "fallback_scene"

    manager._state.recovery_count_by_scene[anchor_id] = 3
    assert manager._select_policy("fallback_scene", anchor_id) == "hard_reset_to_anchor"
