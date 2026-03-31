from rpg.models.npc import NPC


def derive_tone(npc: NPC, target: NPC):
    rel = npc.memory["relationships"].get(target.id, 0)

    if rel > 5:
        return "friendly"
    elif rel < -5:
        return "hostile"
    else:
        return "neutral"

def build_dialogue_input(npc: NPC, target: NPC, scene):
    return {
        "npc_personality": npc.personality,
        "npc_goal": npc.current_goal.type if npc.current_goal else "none",
        "tone": derive_tone(npc, target),
        "scene_summary": scene.summary
    }