from rpg.models.npc import NPC

def build_prompt(npc: NPC, scene, memory):
    return f"""
NPC Personality: {npc.personality}
Goal: {npc.current_goal.type if npc.current_goal else 'none'}
Scene: {scene.summary}
Recent Memory: {memory}

Respond with action and dialogue.
"""