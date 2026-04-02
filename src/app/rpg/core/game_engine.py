"""Game Engine — Single entry point for the RPG system.

PHASE 1 — STABILIZE Step 6:
This is the SINGLE entry point for all game operations as specified in rpg-design.txt.

All other entry points (main.py, player_loop.py run methods, etc.) are DEPRECATED
and should route through this class.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.

Usage:
    engine = GameEngine(
        intent_parser=MyParser(),
        world=MyWorld(),
        npc_system=MyNPCs(),
        story_director=MyDirector(),
        scene_renderer=MyRenderer(),
    )
    scene = engine.handle_input("look around")
"""

from typing import Any, Callable, Dict, List, Optional

from .event_bus import EventBus
from .game_loop import (
    GameLoop,
    IntentParser,
    NPCSystem,
    SceneRenderer,
    StoryDirector,
    TickContext,
    WorldSystem,
)


class GameEngine:
    """Single entry point for the RPG game system.

    This class wraps the GameLoop and EventBus to provide a clean,
    single-interface API for game operations.

    Before this refactor:
        - Multiple entry points existed (main.py, run methods, etc.)
        - Systems were initialized in various places
        - Event buses were scattered

    After this refactor:
        - All game operations go through GameEngine
        - Single EventBus instance is shared across all systems
        - Game loop is the only execution authority
    """

    def __init__(
        self,
        intent_parser: Optional[IntentParser] = None,
        world: Optional[WorldSystem] = None,
        npc_system: Optional[NPCSystem] = None,
        story_director: Optional[StoryDirector] = None,
        scene_renderer: Optional[SceneRenderer] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize the GameEngine with all required subsystems.

        Args:
            intent_parser: Converts player input to structured intents.
            world: World simulation system.
            npc_system: NPC management system.
            story_director: Narrative/story director.
            scene_renderer: Renders final scene output.
            event_bus: Optional external EventBus. If None, creates internal one.
        """
        self.event_bus = event_bus or EventBus()

        self.loop = GameLoop(
            intent_parser=intent_parser,
            world=world,
            npc_system=npc_system,
            event_bus=self.event_bus,
            story_director=story_director,
            scene_renderer=scene_renderer,
        )

    def handle_input(self, player_input: str) -> Dict[str, Any]:
        """Process player input and return the resulting scene.

        This is the PRIMARY entry point for all game interaction.

        Args:
            player_input: Raw player input string.

        Returns:
            The rendered scene dictionary.
        """
        return self.loop.tick(player_input)

    @property
    def event_bus(self) -> EventBus:
        """Access the shared EventBus instance."""
        return self._event_bus

    @event_bus.setter
    def event_bus(self, bus: EventBus) -> None:
        """Set the EventBus instance."""
        self._event_bus = bus

    @property
    def game_loop(self) -> GameLoop:
        """Access the internal GameLoop."""
        return self.loop

    @property
    def tick_count(self) -> int:
        """Number of ticks processed so far."""
        return self.loop.tick_count

    def reset(self) -> None:
        """Reset the engine state (clears loops, events, tick count)."""
        self.loop.reset()
        self.event_bus.reset()

    # Convenient hook registrations delegate to GameLoop

    def on_pre_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a pre-tick callback.

        Args:
            callback: Function called before the tick pipeline runs.
        """
        self.loop.on_pre_tick(callback)

    def on_post_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a post-tick callback.

        Args:
            callback: Function called after the tick pipeline completes.
        """
        self.loop.on_post_tick(callback)

    def on_event(self, callback: Callable) -> None:
        """Register an event callback.

        Args:
            callback: Function called for each event.
        """
        self.loop.on_event(callback)