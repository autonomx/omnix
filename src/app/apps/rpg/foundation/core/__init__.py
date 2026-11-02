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
# PHASE 5.2 — DETERMINISTIC CLOCK + DETERMINISM

# PHASE 5.8 — HOST/PROCESS BOUNDARY

# PHASE 5.6 — LLM BOUNDARY HARDENING

# PHASE 5.3 — LLM RECORD/REPLAY LAYER

# PHASE 5.5 — STATE BOUNDARIES + EFFECT ISOLATION

# PHASE 3 — BRANCHING TIMELINES

# PHASE 4 — TIMELINE QUERY + BRANCH EVALUATION

# PHASE 5.7 — TOOL/RUNTIME BOUNDARY
