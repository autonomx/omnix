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

from .future_simulator import FutureSimulator
from .sandbox import SimulationResult, SimulationSandbox


def apply_events(session, events):
    """Apply a list of events to the session state.
    
    This is a stub implementation for pipeline compatibility.
    The actual event application is handled by the execution pipeline.
    
    Args:
        session: The game session.
        events: List of events to apply.
    """
    for event in events:
        event_type = event.get("type", "")
        if event_type == "damage" and hasattr(session, 'player'):
            target = event.get("target", "")
            amount = event.get("amount", 0)
            if target == "player" and hasattr(session.player, 'hp'):
                session.player.hp = max(0, session.player.hp - amount)


def process(session, intent):
    """Process an intent through the simulation.
    
    This is a stub implementation for pipeline compatibility.
    
    Args:
        session: The game session.
        intent: The intent to process.
        
    Returns:
        Dict with events list and result info.
    """
    action = intent.get("action", "unknown")
    target = intent.get("target", "")
    source = intent.get("source", "")
    
    events = []
    if action in ("attack", "hit", "damage"):
        events.append({
            "type": "damage",
            "source": source,
            "target": target,
            "amount": 10,
        })
    
    return {
        "events": events,
        "action": action,
        "target": target,
    }


def find_npc(session, npc_id):
    """Find an NPC by their ID in the session.

    Args:
        session: The game session.
        npc_id: The NPC ID to find.

    Returns:
        The NPC object or None if not found.
    """
    for npc in session.npcs:
        if npc.id == npc_id:
            return npc
    return None


__all__ = [
    "SimulationSandbox",
    "SimulationResult",
    "FutureSimulator",
    "apply_events",
    "process",
    "find_npc",
]
