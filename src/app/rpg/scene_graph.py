"""
Scene graph module for structured world state representation.

Provides a queryable snapshot of the world state at any point in time,
enabling structured context for LLM generation and future features
like vision systems, memory queries, and spatial reasoning.
"""


def build_scene_graph(session):
    """Build a structured scene graph from the current game session.

    Returns a dict containing:
    - time: current world time
    - entities: list of entity snapshots with id, position, hp, and emotional state
    """
    graph = {
        "time": session.world.time,
        "entities": []
    }

    for npc in session.npcs:
        graph["entities"].append({
            "id": npc.id,
            "pos": npc.position,
            "hp": npc.hp,
            "active": npc.is_active,
            "state": npc.emotional_state
        })

    return graph


def get_entity_by_id(graph, entity_id):
    """Retrieve entity from scene graph by ID."""
    for entity in graph["entities"]:
        if entity["id"] == entity_id:
            return entity
    return None


def get_active_entities(graph):
    """Get list of active entities from scene graph."""
    return [e for e in graph["entities"] if e.get("active", True)]


def get_entity_positions(graph):
    """Get dictionary of entity positions from scene graph."""
    return {e["id"]: e["pos"] for e in graph["entities"]}


def format_scene_context(graph):
    """Format scene graph as text context for LLM prompts."""
    lines = [f"TIME: {graph['time']}", ""]
    lines.append("ENTITIES:")

    for entity in graph["entities"]:
        state = entity.get("state", {})
        mood = _get_mood_from_state(state)
        lines.append(
            f"  - {entity['id']} at {entity['pos']}, "
            f"HP: {entity['hp']}, "
            f"mood: {mood}"
        )

    return "\n".join(lines)


def _get_mood_from_state(emotional_state):
    """Derive a simple mood label from continuous emotional state."""
    anger = emotional_state.get("anger", 0.0)
    fear = emotional_state.get("fear", 0.0)

    if anger > 1.5:
        return "angry"
    elif fear > 1.5:
        return "afraid"
    elif anger > 0.5 or fear > 0.5:
        return "tense"
    else:
        return "calm"