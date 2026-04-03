"""PHASE 4.5 — Simulation Sandbox (ISOLATED ENGINE)

Provides fully isolated simulation environments for "what-if" branching,
forward planning, and AI-driven narrative evaluation.

Core capabilities:
- SimulationSandbox: Isolated game loop for hypothesis testing
- FutureSimulator: Run multiple candidate futures in parallel
- NEVER mutates real game state

Design rules:
- Uses factory pattern to create FRESH engine instances
- Replays base timeline to reconstruct current state
- Injects hypothetical events and simulates forward
- Returns SimulationResult with events and final tick

This module is CRITICAL for:
- NPC decision-making (simulate 3-5 futures, choose best)
- Narrative intelligence (AI evaluates timeline branches)
- Planning AI system (forward simulation with scoring)
"""

from .sandbox import SimulationSandbox, SimulationResult
from .future_simulator import FutureSimulator

__all__ = [
    "SimulationSandbox",
    "SimulationResult",
    "FutureSimulator",
]