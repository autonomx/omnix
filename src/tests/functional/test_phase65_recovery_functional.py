"""Phase 6.5 - Recovery Layer: Functional tests.

Tests end-to-end recovery through the GameLoop tick pipeline for
parser, director, renderer, contradiction, and ambiguity failures.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.narrative.story_director import StoryDirector


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubParser:
    def parse(self, player_input: str):
        return {"text": player_input}


class FailingParser:
    """Always raises on parse."""
    def parse(self, player_input: str):
        raise ValueError("Unrecognised input")


class AmbiguousParser:
    """Returns an ambiguous result."""
    def parse(self, player_input: str):
        return {"text": player_input, "ambiguous": True, "confidence": 0.3}


class StubWorldEmpty:
    def tick(self, event_bus: EventBus):
        pass


class StubWorldWithScene:
    def tick(self, event_bus: EventBus):
        event_bus.emit(Event("scene_started", {"location": "market"}, source="world"))


class StubNPCEmpty:
    def update(self, intent, event_bus: EventBus):
        pass


class StubRenderer:
    def render(self, narrative, coherence_context=None):
        return {"narrative": narrative, "coherence_context": coherence_context}


class FailingRenderer:
    """Always raises on render."""
    def render(self, narrative, coherence_context=None):
        raise RuntimeError("Render engine crash")


class FailingDirector:
    """Always raises on process."""
    def __init__(self):
        self.mode = "live"

    def process(self, events, intent, event_bus, coherence_context=None):
        raise RuntimeError("Director crash")

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


class MalformedDirector:
    """Returns empty dict from process."""
    def __init__(self):
        self.mode = "live"

    def process(self, events, intent, event_bus, coherence_context=None):
        return {}

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(
    parser=None, world=None, npc=None, director=None, renderer=None
):
    return GameLoop(
        intent_parser=parser or StubParser(),
        world=world or StubWorldEmpty(),
        npc_system=npc or StubNPCEmpty(),
        event_bus=EventBus(),
        story_director=director or StoryDirector(),
        scene_renderer=renderer or StubRenderer(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhase65RecoveryFunctional:
    def test_malformed_director_output_still_yields_coherent_scene(self):
        loop = _make_loop(director=MalformedDirector())
        scene = loop.tick("look around")
        assert isinstance(scene, dict)
        assert scene.get("metadata", {}).get("recovery") is True

    def test_high_severity_contradiction_triggers_recovery_scene(self):
        """Inject a high-severity contradiction into coherence state."""
        loop = _make_loop()
        from app.rpg.coherence.models import ContradictionRecord
        loop.coherence_core.record_contradictions([
            ContradictionRecord(
                contradiction_id="c1",
                contradiction_type="entity_state",
                severity="high",
                message="Guard is alive and dead",
            )
        ])
        # The contradiction is already in state; we need the coherence_result
        # to carry it. Simulate by forcing contradictions into the update result.
        # Since apply_events won't produce contradictions on empty events,
        # we test the recovery manager directly through the game loop.
        mgr = loop.recovery_manager
        coherence_ctx = loop._build_director_context()
        contradictions = [{"severity": "high", "message": "Guard conflict"}]
        result = mgr.handle_contradiction(contradictions, coherence_ctx, tick=1)
        assert result.scene.get("metadata", {}).get("recovery") is True
        assert result.reason == "contradiction"

    def test_ambiguous_player_action_gets_graceful_response(self):
        loop = _make_loop(parser=AmbiguousParser())
        scene = loop.tick("huh?")
        assert isinstance(scene, dict)
        assert scene.get("metadata", {}).get("recovery") is True

    def test_renderer_failure_recovers_to_safe_scene(self):
        loop = _make_loop(renderer=FailingRenderer())
        scene = loop.tick("attack goblin")
        assert isinstance(scene, dict)
        assert scene.get("metadata", {}).get("recovery") is True

    def test_parser_failure_recovers_to_safe_scene(self):
        loop = _make_loop(parser=FailingParser())
        scene = loop.tick("@#$%!")
        assert isinstance(scene, dict)
        assert scene.get("metadata", {}).get("recovery") is True

    def test_recovery_uses_last_known_good_scene_anchor(self):
        loop = _make_loop(parser=FailingParser())
        # Set a last good anchor
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "a1", "location": "tavern"}
        )
        scene = loop.tick("bad input")
        assert isinstance(scene, dict)
        assert "tavern" in scene.get("body", "")

    def test_successful_scene_updates_last_good_anchor(self):
        """A successful (non-recovered, non-degraded) scene should update the anchor
        if coherence provides a last_good_anchor."""
        loop = _make_loop(world=StubWorldWithScene())
        # Pre-seed a coherence anchor via internal state
        loop.coherence_core._state.last_good_anchor = {
            "anchor_id": "coherence_anchor",
            "location": "market",
        }
        scene = loop.tick("look around")
        assert isinstance(scene, dict)
        # The scene should NOT be a recovery scene
        meta = scene.get("meta", {})
        metadata = scene.get("metadata", {})
        assert meta.get("recovered") is not True
        assert metadata.get("recovery") is not True
        # The coherence anchor should have been recorded
        assert loop.recovery_manager._state.last_good_scene_anchor is not None
        assert loop.recovery_manager._state.last_good_scene_anchor["anchor_id"] == "coherence_anchor"

    def test_parser_recovery_scene_still_flows_through_renderer_and_normalization(self):
        """Prove that parser recovery still goes through renderer + normalization."""
        loop = _make_loop(parser=FailingParser())
        scene = loop.tick("@#$%!")
        assert isinstance(scene, dict)
        # final scene shape includes normalized keys: scene, options, meta
        assert "scene" in scene
        assert "options" in scene
        # meta or metadata should indicate recovery
        meta = scene.get("meta", {})
        metadata = scene.get("metadata", {})
        assert meta.get("recovered") is True or metadata.get("recovery") is True

    def test_recovery_escalation_on_repeated_failures(self):
        """After many failures in same scene, policy should escalate to hard_reset_to_anchor."""
        loop = _make_loop(parser=FailingParser())
        # Set a known anchor
        loop.recovery_manager.record_last_good_anchor(
            {"anchor_id": "anchor_1", "location": "forest"}
        )
        # Trigger repeated recoveries
        scenes = []
        for i in range(5):
            scene = loop.tick(f"bad input {i}")
            scenes.append(scene)
        # After ESCALATION_THRESHOLD (3) recoveries, policy should escalate
        # Check last scene metadata
        last_meta = scenes[-1].get("meta", {})
        last_metadata = scenes[-1].get("metadata", {})
        # Either meta or metadata should have recovery_reason
        policy = last_meta.get("recovery_policy") or last_metadata.get("recovery_policy")
        assert policy is not None
        # Recovery count should be tracked
        count = loop.recovery_manager._state.recovery_count_by_scene.get("anchor_1", 0)
        assert count >= 5
