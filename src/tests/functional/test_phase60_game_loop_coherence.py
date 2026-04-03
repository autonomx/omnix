"""Phase 6.0 - Coherence Core: Functional tests.

Tests end-to-end coherence integration through the GameLoop,
StoryDirector, and cross-system event flow.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.narrative.story_director import StoryDirector


# ---------------------------------------------------------------------------
# Minimal stubs for GameLoop integration
# ---------------------------------------------------------------------------

class StubParser:
    def parse(self, player_input: str):
        return {"text": player_input}


class StubWorldWithScene:
    """Emits a scene_started event on each tick."""
    def tick(self, event_bus: EventBus):
        event_bus.emit(Event("scene_started", {"location": "market"}, source="world"))


class StubNPCSystem:
    """Emits npc_moved and quest_started events."""
    def update(self, intent, event_bus: EventBus):
        event_bus.emit(Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="npc"))
        event_bus.emit(Event("quest_started", {"quest_id": "q1", "title": "Watch the gate"}, source="npc"))


class StubRenderer:
    def render(self, narrative, coherence_context=None):
        return {
            "narrative": narrative,
            "coherence_context": coherence_context,
        }


class StubRendererNoCoherence:
    """Renderer that doesn't accept coherence_context (backwards compat test)."""
    def render(self, narrative):
        return {"narrative": narrative}


class StubWorldEmpty:
    def tick(self, event_bus: EventBus):
        pass


class StubNPCEmpty:
    def update(self, intent, event_bus: EventBus):
        pass


class StubNPCWithDeath:
    """Emits character_died then npc_moved for a dead character."""
    def update(self, intent, event_bus: EventBus):
        event_bus.emit(Event("character_died", {"entity_id": "guard"}, source="npc"))
        event_bus.emit(Event("npc_moved", {"npc_id": "guard", "location": "afterlife"}, source="npc"))


class StubNPCWithRelationship:
    """Emits relationship_changed event."""
    def update(self, intent, event_bus: EventBus):
        event_bus.emit(Event(
            "relationship_changed",
            {"npc_id": "guard", "target_id": "player", "relationship": 0.8},
            source="npc",
        ))


class StubNPCWithItems:
    """Emits item_acquired event."""
    def update(self, intent, event_bus: EventBus):
        event_bus.emit(Event("item_acquired", {"actor_id": "player", "item_id": "sword"}, source="npc"))


# ---------------------------------------------------------------------------
# Functional Tests
# ---------------------------------------------------------------------------

class TestGameLoopCoherenceIntegration:
    """Test that GameLoop correctly populates coherence context."""

    def test_coherence_context_populated(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldWithScene(),
            npc_system=StubNPCSystem(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("look around")
        coherence = scene.get("coherence_context") or scene.get("coherence", {})
        assert coherence is not None
        scene_summary = coherence.get("scene_summary", {})
        assert scene_summary.get("location") == "market"

    def test_unresolved_threads_tracked(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldWithScene(),
            npc_system=StubNPCSystem(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("look around")
        coherence = scene.get("coherence_context") or scene.get("coherence", {})
        threads = coherence.get("unresolved_threads", [])
        assert any(t.get("thread_id") == "q1" for t in threads)

    def test_multi_tick_coherence(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldWithScene(),
            npc_system=StubNPCSystem(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.tick("tick 1")
        scene = loop.tick("tick 2")
        coherence = scene.get("coherence_context") or scene.get("coherence", {})
        assert coherence.get("scene_summary", {}).get("location") == "market"

    def test_coherence_contradictions_in_scene(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCWithDeath(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("look around")
        contradictions = scene.get("coherence_contradictions", [])
        assert len(contradictions) > 0

    def test_backward_compat_renderer(self):
        """Ensure older renderers without coherence_context still work."""
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRendererNoCoherence(),
        )
        scene = loop.tick("test")
        assert "narrative" in scene

    def test_relationship_tracked_in_coherence(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCWithRelationship(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("talk")
        # Verify relationship fact is in coherence state
        facts = loop.coherence_core.get_known_facts("guard")["facts"]
        rel_facts = [f for f in facts if "relationship" in f["predicate"]]
        assert len(rel_facts) == 1

    def test_item_tracked_in_coherence(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCWithItems(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("take sword")
        facts = loop.coherence_core.get_known_facts("sword")["facts"]
        owner_facts = [f for f in facts if f["predicate"] == "owner"]
        assert owner_facts[0]["value"] == "player"

    def test_coherence_core_accessible_from_loop(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        assert loop.coherence_core is not None


class TestStoryDirectorCoherenceIntegration:
    """Test StoryDirector coherence_context handling."""

    def test_director_accepts_coherence_context(self):
        director = StoryDirector()
        bus = EventBus()
        coherence_ctx = {
            "scene_summary": {"location": "tavern"},
            "active_tensions": [],
            "unresolved_threads": [],
            "recent_consequences": [],
            "last_good_anchor": None,
            "contradictions": [],
        }
        scene = director.process([], {}, bus, coherence_context=coherence_ctx)
        assert isinstance(scene, dict)

    def test_director_builds_own_context_without_core(self):
        director = StoryDirector()
        bus = EventBus()
        scene = director.process([], {}, bus)
        assert isinstance(scene, dict)

    def test_director_with_coherence_core(self):
        from app.rpg.coherence import CoherenceCore
        core = CoherenceCore()
        core.apply_event(
            Event("scene_started", {"location": "forest"}, source="test", event_id="e1", tick=1)
        )
        director = StoryDirector(coherence_core=core)
        bus = EventBus()
        scene = director.process([], {}, bus)
        assert isinstance(scene, dict)

    def test_set_coherence_core(self):
        from app.rpg.coherence import CoherenceCore
        director = StoryDirector()
        assert director.coherence_core is None
        core = CoherenceCore()
        director.set_coherence_core(core)
        assert director.coherence_core is core

    def test_serialize_deserialize_director(self):
        director = StoryDirector()
        bus = EventBus()
        director.process([], {}, bus)
        state = director.serialize_state()
        assert state["tick_count"] == 1

        new_director = StoryDirector()
        new_director.deserialize_state(state)
        assert new_director._tick_count == 1

    def test_set_mode_director(self):
        director = StoryDirector()
        director.set_mode("replay")
        assert director.mode == "replay"


class TestCoherenceModeIntegration:
    """Test coherence mode propagation through GameLoop."""

    def test_set_mode_propagates_to_coherence(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.set_mode("replay")
        assert loop.coherence_core.mode == "replay"

    def test_set_mode_live(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.set_mode("replay")
        loop.set_mode("live")
        assert loop.coherence_core.mode == "live"
