from rpg.spatial import is_near
from rpg.simulation import find_npc


def update_memory(session, events):
    for npc in session.npcs:
        for event in events:
            if can_perceive(npc, event):
                event_copy = {
                    "type": event["type"],
                    "actor": event.get("source"),
                    "target": event.get("target"),
                    "meaning": interpret_event(npc, event),
                    "tick": session.world.time
                }
                npc.memory.append(event_copy)
                npc.memory = npc.memory[-50:]


def can_perceive(npc, event):
    target = find_npc(npc.session, event.get("target"))
    if not target:
        return True
    return is_near(npc.position, target.position)


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

    # recency boost (decay instead of growth)
    current_tick = max(e.get("tick", 0) for e in npc.memory) if npc.memory else 0
    age = current_tick - event.get("tick", 0)
    score += max(0, 5 - age * 0.5)

    # importance
    if event["type"] == "death":
        score += 5

    return score