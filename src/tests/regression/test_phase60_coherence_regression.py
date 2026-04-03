"""Phase 6.0 - Coherence Core: Regression tests.

These tests ensure that the coherence system does not break existing
functionality and that edge cases are handled correctly across ticks.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.narrative.story_director import StoryDirector
from app.rpg.coherence import CoherenceCore, CoherenceState, FactRecord


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubParser:
    def parse(self, player_input: str):
        return {"text": player_input}


class StubWorldEmpty:
    def tick(self, event_bus: EventBus):
        pass


class StubNPCEmpty:
    def update(self, intent, event_bus: EventBus):
        pass


class StubRenderer:
    def render(self, narrative, coherence_context=None):
        return {"narrative": narrative, "coherence_context": coherence_context}


class StubRendererLegacy:
    """Simulates old-style renderer without coherence_context param."""
    def render(self, narrative):
        return {"narrative": narrative}


class StubWorldWithScene:
    def tick(self, event_bus: EventBus):
        event_bus.emit(Event("scene_started", {"location": "market"}, source="world"))


class StubNPCWithQuest:
    def __init__(self):
        self._count = 0

    def update(self, intent, event_bus: EventBus):
        self._count += 1
        if self._count == 1:
            event_bus.emit(Event("quest_started", {"quest_id": "q1", "title": "Find relic"}, source="npc"))
        elif self._count == 2:
            event_bus.emit(Event("quest_completed", {"quest_id": "q1"}, source="npc"))


class StubNPCMultiEvent:
    """Emits multiple events to stress test coherence processing."""
    def update(self, intent, event_bus: EventBus):
        event_bus.emit(Event("npc_moved", {"npc_id": "a", "location": "L1"}, source="npc"))
        event_bus.emit(Event("npc_moved", {"npc_id": "b", "location": "L2"}, source="npc"))
        event_bus.emit(Event("npc_moved", {"npc_id": "c", "location": "L3"}, source="npc"))
        event_bus.emit(Event("item_acquired", {"actor_id": "player", "item_id": "key"}, source="npc"))
        event_bus.emit(Event("relationship_changed", {"npc_id": "a", "target_id": "b", "relationship": 0.5}, source="npc"))


# ---------------------------------------------------------------------------
# Regression Tests
# ---------------------------------------------------------------------------

class TestCoherenceDoesNotBreakExistingLoop:
    """Ensure the game loop still works as before with coherence added."""

    def test_tick_returns_scene_dict(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        result = loop.tick("test")
        assert isinstance(result, dict)

    def test_tick_count_increments(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.tick("tick1")
        loop.tick("tick2")
        assert loop.tick_count == 2

    def test_legacy_renderer_compat(self):
        """Old renderers without coherence_context param still work via TypeError fallback."""
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRendererLegacy(),
        )
        result = loop.tick("test")
        assert "narrative" in result

    def test_pre_post_tick_hooks_still_fire(self):
        pre_calls = []
        post_calls = []

        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.on_pre_tick(lambda ctx: pre_calls.append(ctx.tick_number))
        loop.on_post_tick(lambda ctx: post_calls.append(ctx.tick_number))
        loop.tick("test")
        assert pre_calls == [1]
        assert post_calls == [1]

    def test_event_callback_still_fires(self):
        events_collected = []

        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldWithScene(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.on_event(lambda e: events_collected.append(e.type))
        loop.tick("test")
        assert "scene_started" in events_collected

    def test_reset_clears_tick_count(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.tick("tick1")
        loop.reset()
        assert loop.tick_count == 0


class TestCoherenceStateConsistency:
    """Ensure coherence state stays consistent across multi-tick scenarios."""

    def test_quest_start_and_resolve(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCWithQuest(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.tick("start quest")
        threads = loop.coherence_core.get_unresolved_threads()
        assert any(t["thread_id"] == "q1" for t in threads)

        loop.tick("complete quest")
        threads = loop.coherence_core.get_unresolved_threads()
        active = [t for t in threads if t["status"] != "resolved"]
        assert not any(t["thread_id"] == "q1" for t in active)

    def test_multiple_entities_tracked(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldEmpty(),
            npc_system=StubNPCMultiEvent(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        loop.tick("observe")
        for npc_id, expected_loc in [("a", "L1"), ("b", "L2"), ("c", "L3")]:
            facts = loop.coherence_core.get_known_facts(npc_id)["facts"]
            loc = [f for f in facts if f["predicate"] == "location"]
            assert loc[0]["value"] == expected_loc

    def test_coherence_serialization_roundtrip(self):
        core = CoherenceCore()
        core.apply_event(Event("npc_moved", {"npc_id": "guard", "location": "gate"}, source="test", event_id="e1", tick=1))
        core.apply_event(Event("quest_started", {"quest_id": "q1", "title": "Quest"}, source="test", event_id="e2", tick=2))
        data = core.serialize()

        new_core = CoherenceCore()
        new_core.deserialize(data)

        assert new_core.get_known_facts("guard")["facts"][0]["value"] == "gate"
        assert len(new_core.get_unresolved_threads()) == 1

    def test_authority_hierarchy_after_serialization(self):
        core = CoherenceCore()
        core.insert_fact(FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate", authority="creator_canon",
        ))
        data = core.serialize()

        new_core = CoherenceCore()
        new_core.deserialize(data)
        new_core.apply_event(
            Event("npc_moved", {"npc_id": "guard", "location": "tower"}, source="test", event_id="e1", tick=1)
        )
        facts = new_core.get_known_facts("guard")["facts"]
        loc = [f for f in facts if f["predicate"] == "location"]
        # creator_canon authority should protect the fact
        assert loc[0]["value"] == "gate"


class TestCoherenceEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_events_no_crash(self):
        core = CoherenceCore()
        result = core.apply_events([])
        assert result.events_applied == 0

    def test_unknown_event_type_ignored(self):
        core = CoherenceCore()
        result = core.apply_event(
            Event("custom_unknown_event", {"data": "value"}, source="test", event_id="e1", tick=1)
        )
        assert result.events_applied == 1
        assert len(result.mutations) == 0

    def test_duplicate_facts_update_in_place(self):
        core = CoherenceCore()
        core.apply_event(Event("npc_moved", {"npc_id": "guard", "location": "gate"}, source="test", event_id="e1", tick=1))
        core.apply_event(Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="test", event_id="e2", tick=2))
        facts = core.get_known_facts("guard")["facts"]
        loc = [f for f in facts if f["predicate"] == "location"]
        assert len(loc) == 1
        assert loc[0]["value"] == "market"

    def test_many_anchors_capped(self):
        core = CoherenceCore()
        for i in range(60):
            core.apply_event(
                Event("scene_started", {"location": f"loc{i}"}, source="test", event_id=f"e{i}", tick=i)
            )
        assert len(core.state.continuity_anchors) <= 50

    def test_many_contradictions_capped(self):
        core = CoherenceCore()
        core.apply_event(Event("character_died", {"entity_id": "guard"}, source="test", event_id="e0", tick=0))
        for i in range(210):
            core.apply_event(
                Event("npc_moved", {"npc_id": "guard", "location": f"loc{i}"}, source="test", event_id=f"e{i+1}", tick=i+1)
            )
        assert len(core.state.contradictions) <= 200

    def test_director_coherence_context_has_expected_keys(self):
        director = StoryDirector()
        ctx = director._build_coherence_context()
        assert "scene_summary" in ctx
        assert "active_tensions" in ctx
        assert "unresolved_threads" in ctx
        assert "recent_consequences" in ctx
        assert "last_good_anchor" in ctx
        assert "contradictions" in ctx

    def test_gameloop_coherence_result_in_scene(self):
        loop = GameLoop(
            intent_parser=StubParser(),
            world=StubWorldWithScene(),
            npc_system=StubNPCEmpty(),
            event_bus=EventBus(),
            story_director=StoryDirector(),
            scene_renderer=StubRenderer(),
        )
        scene = loop.tick("test")
        assert "coherence" in scene or "coherence_context" in scene
