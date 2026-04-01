"""Entity Lookup - Centralized utility for finding entities in the session.

This module provides a single source of truth for finding NPCs and players
by their ID, preventing logic drift from duplicated find_npc implementations.

Usage:
    from rpg.utils.entity_lookup import find_entity, find_npc

    # Find any entity (player or NPC)
    entity = find_entity(session, "player")
    entity = find_entity(session, "npc_1")

    # Convenience function for NPC lookup (common case)
    npc = find_npc(session, "npc_1")
"""


def find_entity(session, entity_id):
    """Find an entity by their ID in the session.
    
    Args:
        session: The current game session containing player and npcs.
        entity_id: The ID of the entity to find. Use "player" for the player.
        
    Returns:
        The entity (player or NPC) if found, None otherwise.
    """
    if entity_id == "player":
        return session.player
    return next((n for n in session.npcs if n.id == entity_id), None)


# Convenience alias for common NPC lookup pattern
find_npc = find_entity