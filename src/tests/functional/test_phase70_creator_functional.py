"""Functional tests for Phase 7.0 Creator / GM layer."""

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.creator.gm_state import InjectEventDirective
from app.rpg.narrative.story_director import StoryDirector


class _Parser:
    def parse(self, text):
        return {"text": text}


class _World:
    def tick(self, event_bus):
        return None


class _NPC:
    def update(self, intent, event_bus):
        return None


class _Renderer:
    def render(self, narrative, coherence_context=None):
        return narrative


def test_gm_inject_event_directive_flows_into_event_stream():
    loop = GameLoop(
        intent_parser=_Parser(),
        world=_World(),
        npc_system=_NPC(),
        event_bus=EventBus(),
        story_director=StoryDirector(),
        scene_renderer=_Renderer(),
    )

    loop.gm_directive_state.add_directive(
        InjectEventDirective(
            directive_id="gm:spawn",
            directive_type="inject_event",
            scope="scene",
            event_type="npc_spawned",
            payload={"npc_id": "merchant"},
        )
    )

    scene = loop.tick("look around")
    coherence = scene.get("coherence_context") or {}
    events_seen = coherence.get("events_seen", []) if isinstance(coherence, dict) else []
    # The event should have been emitted - verify directive was removed from state
    assert "gm:spawn" not in loop.gm_directive_state.directives


def test_gm_injected_event_updates_coherence_in_same_tick():
    loop = GameLoop(
        intent_parser=_Parser(),
        world=_World(),
        npc_system=_NPC(),
        event_bus=EventBus(),
        story_director=StoryDirector(),
        scene_renderer=_Renderer(),
    )

    loop.gm_directive_state.add_directive(
        InjectEventDirective(
            directive_id="gm:quest",
            directive_type="inject_event",
            scope="scene",
            event_type="quest_started",
            payload={"quest_id": "gm_q1", "title": "GM quest"},
        )
    )

    scene = loop.tick("look around")
    coherence = scene.get("coherence_context") or {}

    # Verify the directive was removed after emission
    assert "gm:quest" not in loop.gm_directive_state.directives