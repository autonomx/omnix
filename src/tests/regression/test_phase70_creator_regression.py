"""Regression tests for Phase 7.0 Creator / GM layer."""

from app.rpg.core.event_bus import EventBus
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


def test_scene_scoped_inject_event_directive_emits_once_and_is_removed():
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
            directive_id="gm:spawn_once",
            directive_type="inject_event",
            scope="scene",
            event_type="npc_spawned",
            payload={"npc_id": "merchant"},
        )
    )

    scene1 = loop.tick("look around")
    scene2 = loop.tick("look around again")

    # First tick should have seen the injected event
    coherence1 = scene1.get("coherence_context") or {}
    events1 = coherence1.get("events_seen", []) if isinstance(coherence1, dict) else []
    # The directive should be removed after first emission
    assert "gm:spawn_once" not in loop.gm_directive_state.directives