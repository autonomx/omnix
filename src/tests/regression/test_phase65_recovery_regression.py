"""Phase 6.5 - Recovery Layer: Regression tests.

Ensures recovery does not spiral, invent entities, bypass replay rules,
or break snapshot compatibility.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.core.snapshot_manager import SnapshotManager
from app.rpg.narrative.story_director import StoryDirector
from app.rpg.recovery.manager import RecoveryManager
from app.rpg.recovery.models import RecoveryState

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubParser:
    def parse(self, player_input: str):
        return {"text": player_input}


class FailingParser:
    def parse(self, player_input: str):
        raise ValueError("parse error")


class StubWorldEmpty:
    def tick(self, event_bus: EventBus):
        pass


class StubNPCEmpty:
    def update(self, intent, event_bus: EventBus):
        pass


class StubRenderer:
    def render(self, narrative, coherence_context=None):
        return {"narrative": narrative, "coherence_context": coherence_context}


class FailingDirector:
    def __init__(self):
        self.mode = "live"

    def process(self, events, intent, event_bus, coherence_context=None):
        raise RuntimeError("director crash")

    def set_mode(self, mode):
        self.mode = mode

    def set_coherence_core(self, core):
        pass

    def set_recovery_manager(self, rm):
        pass

    def serialize_state(self):
        return {}

    def deserialize_state(self, data):
        pass


def _make_loop(parser=None, director=None, renderer=None):
    return GameLoop(
        intent_parser=parser or StubParser(),
        world=StubWorldEmpty(),
        npc_system=StubNPCEmpty(),
        event_bus=EventBus(),
        story_director=director or StoryDirector(),
        scene_renderer=renderer or StubRenderer(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhase65RecoveryRegression:
    def test_repeated_recovery_does_not_spiral(self):
        """Multiple consecutive failures should not grow state unboundedly."""
        loop = _make_loop(parser=FailingParser())
        for i in range(100):
            scene = loop.tick(f"bad input {i}")
            assert isinstance(scene, dict)
        # recent_recoveries should be capped
        assert len(loop.recovery_manager._state.recent_recoveries) <= 50

    def test_recovery_output_remains_grounded_in_coherence_state(self):
        """Recovery scenes should reference coherence data, not invent new context."""
        loop = _make_loop(parser=FailingParser())
        scene = loop.tick("garbled")
        assert isinstance(scene, dict)
        body = scene.get("body", "")
        metadata = scene.get("metadata", {})
        # Should be marked as recovery
        assert metadata.get("recovery") is True
        # Should not contain invented character names or locations not in coherence
        assert "dragon" not in body.lower()
        assert "wizard" not in body.lower()

    def test_recovery_does_not_bypass_replay_rules(self):
        """Setting mode to replay should propagate to recovery manager."""
        loop = _make_loop()
        loop.set_mode("replay")
        assert loop.recovery_manager.mode == "replay"
        loop.set_mode("live")
        assert loop.recovery_manager.mode == "live"

    def test_recovery_state_survives_snapshot_restore(self):
        """Snapshot save/load should preserve recovery state."""
        loop = _make_loop()
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "snap_anchor", "location": "dungeon"}
        )
        loop.recovery_manager.handle_parser_failure(
            player_input="test",
            error="fail",
            coherence_summary={},
            tick=1,
        )

        sm = SnapshotManager()
        sm.save_snapshot(loop, tick=1)

        # Create a fresh loop and restore
        loop2 = _make_loop()
        assert loop2.recovery_manager._state.last_good_scene_anchor is None

        sm.load_snapshot(1, loop2)
        assert loop2.recovery_manager._state.last_good_scene_anchor is not None
        assert loop2.recovery_manager._state.last_good_scene_anchor["anchor_id"] == "snap_anchor"
        assert len(loop2.recovery_manager._state.recent_recoveries) == 1

    def test_recovery_does_not_invent_absent_entities(self):
        """Fallback scenes must not reference entities not present in coherence."""
        mgr = RecoveryManager()
        coherence_summary = {
            "scene_summary": {"location": "forest"},
            "active_tensions": [],
            "unresolved_threads": [],
        }
        result = mgr.handle_director_failure(
            player_input="go north",
            error="timeout",
            coherence_summary=coherence_summary,
        )
        body = result.scene.get("body", "")
        # Should only reference 'forest' from coherence, not any invented entities
        assert "forest" in body
        assert "dragon" not in body.lower()
        assert "goblin" not in body.lower()

    def test_last_good_anchor_not_updated_by_failed_scene(self):
        """A failed scene (recovery scene) must not become the new anchor."""
        loop = _make_loop(director=FailingDirector())
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "original", "location": "tavern"}
        )
        scene = loop.tick("look")
        # Check both meta and metadata for recovered flag
        meta = scene.get("meta", {})
        metadata = scene.get("metadata", {})
        assert meta.get("recovered") is True or metadata.get("recovery") is True
        # Anchor should still be the original, not updated by the failed tick
        assert loop.recovery_manager._state.last_good_scene_anchor["anchor_id"] == "original"

    def test_last_good_anchor_not_updated_by_recovered_scene(self):
        """Prove recovered scenes do not become last-good anchors."""
        loop = _make_loop(parser=FailingParser())
        # Set an initial strong anchor
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "strong_anchor", "location": "castle"}
        )
        # Generate a recovered scene with meta["recovered"] = True
        scene = loop.tick("@#$%!")
        assert isinstance(scene, dict)
        # Verify the scene has recovery metadata
        meta = scene.get("meta", {})
        metadata = scene.get("metadata", {})
        assert meta.get("recovered") is True or metadata.get("recovery") is True
        # call _maybe_record_last_good_anchor(...) directly to confirm behavior
        coherence_context = loop._build_director_context()
        loop._maybe_record_last_good_anchor(scene, coherence_context)
        # confirm stored anchor did not change
        assert loop.recovery_manager._state.last_good_scene_anchor["anchor_id"] == "strong_anchor"

    def test_recovery_state_survives_snapshot_restore_complete(self):
        """Snapshot save/load should preserve all recovery state fields."""
        loop = _make_loop()
        # set a last-good anchor
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "snap_anchor", "location": "dungeon"}
        )
        # record at least one recovery
        loop.recovery_manager.handle_parser_failure(
            player_input="test",
            error="fail",
            coherence_summary={},
            tick=1,
        )
        # generate another to test recovery_count_by_scene
        loop.recovery_manager.handle_director_failure(
            player_input="look",
            error="timeout",
            coherence_summary={},
            tick=2,
        )

        sm = SnapshotManager()
        sm.save_snapshot(loop, tick=5)

        # Create a fresh loop and restore
        loop2 = _make_loop()
        assert loop2.recovery_manager._state.last_good_scene_anchor is None
        assert len(loop2.recovery_manager._state.recent_recoveries) == 0

        sm.load_snapshot(5, loop2)

        # last_good_scene_anchor restored
        assert loop2.recovery_manager._state.last_good_scene_anchor is not None
        assert loop2.recovery_manager._state.last_good_scene_anchor["anchor_id"] == "snap_anchor"

        # recent_recoveries restored (at least the initial save_snapshot tick)
        assert len(loop2.recovery_manager._state.recent_recoveries) >= 1

        # last_recovery_reason restored
        assert loop2.recovery_manager._state.last_recovery_reason == "director_failure"
        assert loop2.recovery_manager._state.last_recovery_tick == 2

        # recovery_count_by_scene restored
        assert isinstance(loop2.recovery_manager._state.recovery_count_by_scene, dict)


def test_last_good_anchor_uses_scene_summary_only_when_anchor_quality_is_sufficient():
    loop = GameLoop(
        intent_parser=StubParser(),
        world=StubWorldEmpty(),
        npc_system=StubNPCEmpty(),
        event_bus=EventBus(),
        story_director=StoryDirector(),
        scene_renderer=StubRenderer(),
    )

    scene = {"scene": "A stable scene", "meta": {}}

    weak_context = {"scene_summary": {}}
    loop._maybe_record_last_good_anchor(scene, weak_context)
    assert loop.recovery_manager._state.last_good_scene_anchor is None

    strong_context = {"scene_summary": {"location": "market", "summary": "Crowded square"}}
    loop._maybe_record_last_good_anchor(scene, strong_context)
    assert loop.recovery_manager._state.last_good_scene_anchor == strong_context["scene_summary"]
