from rpg.models.npc import NPC

def remember_event(npc: NPC, event):
    npc.memory["events"].append(event)

def remember_fact(npc: NPC, fact):
    npc.memory["facts"].append(fact)

def update_relationship(npc: NPC, other: NPC, delta: int):
    npc.memory["relationships"].setdefault(other.id, 0)
    npc.memory["relationships"][other.id] += delta

def retrieve_relevant(npc: NPC, scene):
    return npc.memory["events"][-5:]