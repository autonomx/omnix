"""Core module for RPG system — Phase 4 TIMELINE QUERY + BRANCH EVALUATION.

PHASE 1 — STABILIZE: Single game loop authority, EventBus, StoryDirector.
PHASE 2 — REPLAY ENGINE: Event-sourced save/load, replay, time-travel debug.
PHASE 2.5 — SNAPSHOTS: Deterministic ordering, deduplication, hybrid replay.
PHASE 3 — BRANCHING TIMELINES: DAG-based event causality, multiverse graph.
PHASE 4 — TIMELINE QUERY API: Query, evaluate, simulate branches.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.
"""

# Phase 1 — STABILIZE: New single-authority components
# These are the primary exports for the refactored architecture.
# PHASE 5.2 — DETERMINISTIC CLOCK
from .clock import DeterministicClock
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
from .replay_engine import EventConsumer, ReplayConfig, ReplayEngine
from .snapshot_manager import SnapshotManager, Snapshot

# PHASE 3 — BRANCHING TIMELINES
from .timeline_graph import TimelineGraph, TimelineNode
from .timeline_metadata import TimelineMetadata

# PHASE 4 — TIMELINE QUERY + BRANCH EVALUATION
from .timeline_query import (
    TimelineQueryEngine,
    TimelineSnapshot,
    BranchScore,
    BranchEvaluator,
    DefaultBranchEvaluator,
    EventContext,
    create_intent_event,
)

__all__ = [
    # PHASE 1 — STABILIZE: New single-authority components
    # PHASE 5.2 — DETERMINISTIC CLOCK
    "DeterministicClock",
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
    # PHASE 2 — REPLAY ENGINE
    "ReplayEngine",
    "ReplayConfig",
    "EventConsumer",
    # PHASE 2.5 — SNAPSHOTS & DETERMINISM
    "SnapshotManager",
    "Snapshot",
    # PHASE 3 — BRANCHING TIMELINES
    "TimelineGraph",
    "TimelineNode",
    "TimelineMetadata",
    # PHASE 4 — TIMELINE QUERY + BRANCH EVALUATION
    "TimelineQueryEngine",
    "TimelineSnapshot",
    "BranchScore",
    "BranchEvaluator",
    "DefaultBranchEvaluator",
    "EventContext",
    "create_intent_event",
]
