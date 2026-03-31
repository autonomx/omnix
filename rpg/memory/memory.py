from rpg.models.npc import NPC

def remember_event(npc: NPC, event):
    # Add importance weighting based on emotion
    importance_weights = {
        "angry": 0.9,
        "fearful": 0.8,
        "happy": 0.6,
        "neutral": 0.3
    }
    emotion = event.get("emotion", "neutral")
    importance = importance_weights.get(emotion, 0.3)

    event_with_importance = {**event, "importance": importance}
    npc.memory["events"].append(event_with_importance)

def remember_fact(npc: NPC, fact):
    npc.memory["facts"].append(fact)

def update_relationship(npc: NPC, other: NPC, delta: int):
    npc.memory["relationships"].setdefault(other.id, 0)
    npc.memory["relationships"][other.id] += delta

def retrieve_relevant(npc: NPC, scene):
    return npc.memory["events"][-5:]