"""
Emotion system for NPCs with continuous state, decay, and event influence.

Replaces binary mood flags with continuous emotional dimensions:
- anger: response to being attacked or witnessing violence
- fear: response to threats, allies dying, low HP
- loyalty: bond with allies/faction members
"""


def decay_emotions(npc, world_time):
    """Apply time-based decay to emotional state values.

    Emotions decay exponentially based on elapsed time since last update.
    This ensures NPCs calm down over time rather than staying permanently angry/afraid.
    """
    dt = world_time - npc.emotional_state.get("last_update", world_time)

    for k in ["anger", "fear"]:
        npc.emotional_state[k] *= (0.9 ** dt)

    npc.emotional_state["last_update"] = world_time


def apply_event_emotion(npc, event, intensity=1.0):
    """Apply emotional response to a perceived event.

    Different event types trigger different emotional responses:
    - damage when targeted: increases anger and fear
    - ally killed: increases fear significantly

    Args:
        npc: The NPC receiving the emotional response.
        event: The event that triggered the response.
        intensity: Multiplier for emotional response strength.
            1.0 = normal, 2.0 = doubled (direct victim), 0.5 = halved (attacker)
    """
    if event["type"] == "damage" and event.get("target") == npc.id:
        npc.emotional_state["anger"] += 2.0 * intensity
        npc.emotional_state["fear"] += 0.5 * intensity

    if event["type"] == "ally_killed":
        npc.emotional_state["fear"] += 1.5 * intensity


def apply_event_emotion_with_relationships(npc, event, session):
    """Enhanced emotional response considering NPC relationships.

    Extends basic emotion with relationship awareness:
    - damage from ally: reduces loyalty
    - ally damaged: increases anger toward attacker
    """
    apply_event_emotion(npc, event)

    if event["type"] == "damage":
        target_id = event.get("target")
        source_id = event.get("source")

        # If an ally was attacked, increase anger
        if target_id != npc.id and is_ally(npc, target_id, session):
            npc.emotional_state["anger"] += 1.0

        # If attacked by an ally, reduce loyalty
        if source_id and is_ally(npc, source_id, session):
            npc.emotional_state["loyalty"] -= 1.0


def is_ally(npc, other_id, session):
    """Check if another NPC is an ally of this NPC."""
    ally_ids = npc.relationships.get("allies", [])
    return other_id in ally_ids