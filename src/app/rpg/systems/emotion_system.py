"""Emotion System - Handles NPC emotional responses to events.

Subscribes to:
- "damage": Increases anger and fear for targeted NPCs with intensity weighting
- "death": Increases fear for NPCs who perceive the death

Priority: 0 (default, runs after combat but before memory)

Fixes:
- Uses centralized entity lookup to prevent logic drift
- Distance computed once and cached (no redundant computations)
"""

from rpg.emotion import apply_event_emotion
from rpg.spatial import distance
from rpg.utils.entity_lookup import find_entity as find_npc


def on_damage(session, event):
    """Apply emotional response to damage events for all NPCs.
    
    NPCs that are targeted by damage receive anger and fear increases.
    Intensity weighting applied:
    - Target (being attacked): intensity = 2.0
    - Source (attacker): intensity = 0.5
    - Others (nearby): intensity = 1.0 if within perception radius
    """
    target_id = event.get("target")
    source_id = event.get("source")
    target = find_npc(session, target_id) if target_id else None

    for npc in session.npcs:
        if not npc.is_active:
            continue

        # Calculate emotional intensity based on relationship to event
        intensity = 1.0  # Default for bystanders

        if event.get("target") == npc.id:
            # NPC is the victim - strongest response
            intensity = 2.0
        elif event.get("source") == npc.id:
            # NPC is the attacker - reduced response
            intensity = 0.5
        else:
            # Bystander - check perception radius (spatial filtering)
            if target and target.is_active:
                dist = distance(npc.position, target.position)
                if dist > npc.perception_radius:
                    # Too far to perceive - skip emotional response
                    continue

        apply_event_emotion(npc, event, intensity=intensity)


def on_death(session, event):
    """Apply emotional response when an NPC dies.
    
    Nearby NPCs or allies of the deceased receive fear increases.
    Distance is computed once and cached for reuse.
    """
    target_id = event.get("target")
    target = find_npc(session, target_id)

    for npc in session.npcs:
        if not npc.is_active:
            continue

        # Skip if target is already removed/position unavailable
        if not target or not hasattr(target, 'position'):
            # Still process basic death emotion for all active NPCs
            death_event = {
                "type": "ally_killed",
                "target": target_id,
                "tick": session.world.time
            }
            apply_event_emotion(npc, death_event)
            continue

        # Check if NPC can perceive the death (spatial filtering)
        # Distance is computed once and cached for both checks
        try:
            dist = distance(npc.position, target.position)
            if dist <= npc.perception_radius + 2:
                death_event = {
                    "type": "ally_killed",
                    "target": target_id,
                    "tick": session.world.time
                }
                # Higher intensity if NPC is near the death
                intensity = 2.0 if dist <= 1 else 1.0
                apply_event_emotion(npc, death_event, intensity=intensity)
        except AttributeError:
            pass


def register(bus, session):
    """Register all emotion system handlers with the event bus.
    
    Priority 0 (default) ensures emotion runs after combat (-10)
    but before memory (10).
    """
    bus.subscribe("damage", lambda s, e: on_damage(s, e), priority=0)
    bus.subscribe("death", lambda s, e: on_death(s, e), priority=0)