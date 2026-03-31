def update_memory(session, events):
    for npc in session.npcs:
        for event in events:
            if can_perceive(npc, event):
                npc.memory.append({
                    "type": event["type"],
                    "actor": event.get("source"),
                    "target": event.get("target"),
                    "meaning": interpret_event(npc, event)
                })
                npc.memory = npc.memory[-50:]


def can_perceive(npc, event):
    return True  # TODO: distance/visibility


def interpret_event(npc, event):
    if event["type"] == "damage":
        if event["target"] == npc.id:
            return "I was attacked"
        return "violence nearby"

    if event["type"] == "death":
        return "someone died"

    return "unknown"