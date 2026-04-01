"""Memory System - Handles NPC memory updates from perceived events.

Subscribes to:
- "*": Wildcard - all events are considered for memory recording
- "damage": Relationship update trigger
- "death": Relationship update trigger
- "heal": Relationship update trigger
- "dialogue": Relationship update trigger

Priority: 10 (runs last after state mutations are complete)

Features:
- Spatial perception filtering (NPCs only remember events they can perceive)
- Event type validation before recording
- Uses centralized entity lookup to prevent logic drift
- Memory types (episodic/semantic/relationship) for structured storage
- Relationship system integration (trust, fear, anger tracking)
- Belief system integration (derived truth layer for GOAP/Story)
- Event bus → memory hooks for consistency and decoupling
"""

from rpg.spatial import distance
from rpg.utils.entity_lookup import find_npc as _find_npc
from rpg.memory.relationships import (
    update_relationship_from_event,
)
from rpg.memory.belief_system import BeliefSystem


def find_npc(session, npc_id):
    """Find an NPC by their ID in the session.
    
    Backward-compatible wrapper that delegates to centralized entity lookup.
    """
    return _find_npc(session, npc_id)


def can_perceive(npc, event, session) -> bool:
    """Check if an NPC can perceive an event based on spatial and visibility rules.
    
    Returns True if:
    - Event has no target (global event like weather)
    - Target is not found (assume perceivable)
    - Target is within perception radius
    
    Returns False if:
    - Target exists and is outside perception radius
    """
    target_id = event.get("target")
    if not target_id:
        # Global events (weather, time, etc.) are always perceivable
        return True

    target = find_npc(session, target_id)
    if not target:
        # Target not found - assume perceivable (don't lose memory due to stale refs)
        return True

    return distance(npc.position, target.position) <= npc.perception_radius


def interpret_event(npc, event) -> str:
    """Interpret the meaning of an event from an NPC's perspective."""
    event_type = event.get("type")
    
    if event_type == "damage":
        if event.get("target") == npc.id:
            return "I was attacked"
        elif event.get("source") == npc.id:
            return "I attacked someone"
        else:
            return "violence nearby"
    
    if event_type == "death":
        return "someone died"
    
    if event_type == "heal":
        if event.get("target") == npc.id:
            return "I was healed"
        return "healing nearby"
    
    return "unknown"


def compute_importance(event: dict) -> float:
    """Heuristic importance scoring for events.
    
    Higher values = more memorable.
    - death: 5.0 (highest, stays in memory longest)
    - damage: scales with amount (1.0-3.0)
    - dialogue: 1.5
    - default: 1.0
    """
    etype = event.get("type")
    
    if etype == "death":
        return 5.0
    if etype == "damage":
        return min(3.0, event.get("amount", 1) / 5)
    if etype == "dialogue":
        return 1.5
    if etype == "heal":
        return 2.0
    
    return 1.0


def _build_memory_entry(npc, event, session) -> dict:
    """Build a memory entry with proper type classification.
    
    Creates episodic memories with structured fields for later consolidation.
    
    Args:
        npc: The NPC recording the memory
        event: The event being recorded
        session: Current game session
        
    Returns:
        Memory entry dict with all required fields
    """
    # Build visibility list for future stealth/hidden info support
    visibility = [npc.id]
    target = find_npc(session, event.get("target"))
    source = find_npc(session, event.get("source"))
    if target:
        visibility.append(target.id)
    if source:
        visibility.append(source.id)
    visibility = list(set(visibility))  # dedupe
    
    return {
        "memory_type": "episodic",  # All direct event memories are episodic
        "timestamp": session.world.time,
        "type": event.get("type"),
        "source": event.get("source"),
        "target": event.get("target"),
        "data": dict(event),
        "importance": compute_importance(event),
        "actor": event.get("source"),
        "meaning": interpret_event(npc, event),
        "tick": session.world.time,
        "visibility": visibility,
    }


def on_any_event(session, event):
    """Process any event for NPC memory recording.
    
    Only NPCs that can perceive the event (spatial filtering) add it to memory.
    Memory pruning is applied after processing.
    
    Note: npc.memory is a dict with "events", "facts", "relationships" keys.
    We append to npc.memory["events"].
    """
    from rpg.memory import _prune_memory

    for npc in session.npcs:
        if not npc.is_active:
            continue
        
        # Only record events the NPC can perceive
        if can_perceive(npc, event, session):
            memory_entry = _build_memory_entry(npc, event, session)
            npc.memory["events"].append(memory_entry)

    # Prune memory for all NPCs
    for npc in session.npcs:
        if npc.is_active:
            _prune_memory(npc)


def on_relationship_event(session, event):
    """Update relationship memories from specific event types.
    
    This is the event bus → relationship hook that ensures relationships
    are updated consistently from damage, death, heal, and dialogue events.
    
    Priority: 5 (runs before general memory recording at priority 10)
    """
    for npc in session.npcs:
        if not npc.is_active:
            continue
        
        # Only update relationships for NPCs involved in or perceiving the event
        if can_perceive(npc, event, session):
            update_relationship_from_event(npc, event, session.world.time)


def on_belief_update(session, event):
    """Update belief systems incrementally from specific event types.
    
    TARGETED DISPATCH: Only updates NPCs that are:
    - The source (actor) of the event
    - The target of the event
    - Within perception range (observers)
    
    Uses INCREMENTAL updates (update_from_event) instead of
    full memory rescan (update_from_memories).
    
    Priority: 7 (runs after relationships, before general memory)
    """
    affected_ids = set()
    
    # Collect affected entity IDs
    src = event.get("source") or event.get("actor")
    tgt = event.get("target")
    if src:
        affected_ids.add(src)
    if tgt:
        affected_ids.add(tgt)
    
    for npc in session.npcs:
        if not npc.is_active:
            continue
        
        # TARGETED: Only process NPCs directly involved or perceiving
        npc_involved = npc.id in affected_ids
        
        if npc_involved:
            # Initialize belief system if not present
            if not hasattr(npc, 'belief_system'):
                npc.belief_system = BeliefSystem()
            # INCREMENTAL: Update from single event, not full memory scan
            npc.belief_system.update_from_event(event)
        
        elif can_perceive(npc, event, session):
            # Observer: still update but with lower weight (handled in belief_system)
            if not hasattr(npc, 'belief_system'):
                npc.belief_system = BeliefSystem()
            npc.belief_system.update_from_event(event)


def init_npc_belief_system(npc):
    """Initialize the belief system for an NPC if not already present.
    
    Args:
        npc: The NPC to initialize the belief system for
    """
    if not hasattr(npc, 'belief_system'):
        npc.belief_system = BeliefSystem()


def update_all_beliefs(session):
    """Update beliefs for all active NPCs based on their current memories.
    
    Call this periodically (e.g., every 10 ticks) or after significant events
    to keep beliefs current.
    
    Args:
        session: The current game session
    """
    for npc in session.npcs:
        if not npc.is_active:
            continue
        init_npc_belief_system(npc)
        npc.belief_system.update_from_memories(npc)


def register(bus, session):
    """Register memory system handlers with the event bus.
    
    Priority scheme:
    - Relationship events: priority 5 (updates trust, fear, anger first)
    - Belief updates: priority 7 (derives beliefs from events)
    - General memory: priority 10 (records events after relationship updates)
    
    This ensures relationships are updated before memories are recorded,
    allowing memory entries to reference current relationship state.
    """
    # Register relationship update handlers (priority 5)
    bus.subscribe("damage", on_relationship_event, priority=5)
    bus.subscribe("death", on_relationship_event, priority=5)
    bus.subscribe("heal", on_relationship_event, priority=5)
    bus.subscribe("dialogue", on_relationship_event, priority=5)
    
    # Register belief update handlers (priority 7)
    bus.subscribe("damage", on_belief_update, priority=7)
    bus.subscribe("death", on_belief_update, priority=7)
    bus.subscribe("heal", on_belief_update, priority=7)
    bus.subscribe("assist", on_belief_update, priority=7)
    
    # Register general memory handler (priority 10)
    bus.subscribe("*", on_any_event, priority=10)
