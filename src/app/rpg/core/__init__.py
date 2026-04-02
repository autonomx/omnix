"""Core module for RPG system — Phase 1 STABILIZE.

PHASE 1 — STABILIZE: Single game loop authority, EventBus, StoryDirector.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.
"""

# Phase 1 — STABILIZE: New single-authority components
# These are the primary exports for the refactored architecture.
from .event_bus import Event, EventBus
from .game_loop import (
    GameLoop,
    IntentParser,
    NPCSystem,
    SceneRenderer,
    StoryDirector,
    TickContext,
    TickPhase,
    WorldSystem,
)
from .game_engine import GameEngine

__all__ = [
    # PHASE 1 — STABILIZE: New single-authority components
    "Event",
    "EventBus",
    "GameLoop",
    "GameEngine",
    "IntentParser",
    "NPCSystem",
    "SceneRenderer",
    "StoryDirector",
    "TickContext",
    "TickPhase",
    "WorldSystem",
]
