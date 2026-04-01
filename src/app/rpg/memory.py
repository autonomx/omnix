from rpg.spatial import is_near
from rpg.simulation import find_npc
from rpg.emotion import apply_event_emotion


def update_memory(session, events):
    for npc in session.npcs:
        seen = set()
        for event in events:
            # Prevent duplicate memory events
            key = (event["type"], event.get("source"), event.get("target"))
            if key in seen:
                continue
            seen.add(key)

            if can_perceive(npc, event):
                event_copy = {
                    "type": event["type"],
                    "actor": event.get("source"),
                    "target": event.get("target"),
                    "meaning": interpret_event(npc, event),
                    "tick": session.world.time
                }
                npc.memory.append(event_copy)

                # Apply emotional response to perceived events
                apply_event_emotion(npc, event)

        # Memory pruning: keep important events + recent history
        _prune_memory(npc)


def can_perceive(npc, event):
    source = find_npc(npc.session, event.get("source"))
    target = find_npc(npc.session, event.get("target"))

    ref = source or target
    if not ref:
        return True

    return is_near(npc.position, ref.position)


def interpret_event(npc, event):
    if event["type"] == "damage":
        if event["target"] == npc.id:
            return "I was attacked"
        return "violence nearby"

    if event["type"] == "death":
        return "someone died"

    return "unknown"


def retrieve(npc, query):
    scored = []
    for event in npc.memory:
        score = score_event(npc, event, query)
        scored.append((score, event))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [event for score, event in scored[:10]]


def score_event(npc, event, query):
    score = 0

    if query.get("target") == event.get("target"):
        score += 2

    if query.get("type") == event.get("type"):
        score += 1

    # Use world time as source of truth, not memory
    current_tick = npc.session.world.time
    age = max(0, current_tick - event.get("tick", 0))

    # decay scoring
    score += max(0, 5 - age * 0.5)

    if event["type"] == "death":
        score += 5

    return score


def _prune_memory(npc):
    """Memory pruning: keep important events + recent history (bounded to 100)."""
    # Always keep important events (death, boss_event)
    important = [e for e in npc.memory if e.get("type") in ("death", "boss_event")]

    # Keep last 100 recent events
    recent = npc.memory[-100:]

    # Merge: important events first, then recent, deduplicated by id
    seen = {}
    for e in important + recent:
        seen[id(e)] = e

    npc.memory = list(seen.values())