"""Combat System - Handles damage, death, and combat-related event processing.

Subscribes to:
- "damage": Reduces target HP, publishes "death" event if HP <= 0
- "death": Marks NPC as inactive

Priority: -10 (processes before other systems to mutate state early)

Fixes:
- Uses centralized entity lookup to prevent logic drift
- Death handler owns is_active state transition (no redundant assignment in on_damage)
- Events include metadata for future systems (perception, LLM reasoning, etc.)
"""

from rpg.utils.entity_lookup import find_entity as find_npc


def on_damage(session, event):
    """Handle damage event by reducing target HP.
    
    If target HP drops to 0 or below, publishes a "death" event.
    Note: is_active state transition is handled by the death event handler,
    not here, to avoid redundant state mutations.
    """
    target_id = event.get("target")
    amount = event.get("amount", 0)
    source_id = event.get("source")
    
    # Find the actual target entity
    target = find_npc(session, target_id)
    
    if not target:
        return
    
    # Only process if target is active
    if not getattr(target, "is_active", True):
        return
    
    # Apply damage
    target.hp -= amount
    
    # Check for death - publish event but let death handler own state transition
    if target.hp <= 0:
        session.event_bus.publish({
            "type": "death",
            "target": target_id,
            "source": source_id,
            "tick": session.world.time,
            "meta": {
                "position": getattr(target, "position", None),
                "cause": "damage",
            }
        })


def on_death(session, event):
    """Handle death event by ensuring target is marked inactive."""
    target = find_npc(session, event.get("target"))
    if target:
        target.is_active = False


def register(bus, session):
    """Register all combat system handlers with the event bus.
    
    Priority -10 ensures combat runs before emotion/memory systems.
    """
    bus.subscribe("damage", lambda s, e: on_damage(s, e), priority=-10)
    bus.subscribe("death", lambda s, e: on_death(s, e), priority=-10)
