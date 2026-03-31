from rpg.actions.resolution import Action
from rpg.memory.memory import retrieve_relevant
from rpg.models.npc import NPC
from rpg.npc.goals import select_goal
from rpg.scene.scene import get_enemies


def npc_decide(npc: NPC, scene):
    memory = retrieve_relevant(npc, scene)
    goal = select_goal(npc, scene)
    action = decide_action(npc, goal, scene, memory)
    return action

def decide_action(npc: NPC, goal, scene, memory):
    # Emotion-driven behavior overrides
    if npc.emotional_state.get("angry", 0) > 0.6:
        # Angry NPCs are more aggressive
        enemies = get_enemies(scene, npc)
        if enemies:
            return Action("attack", "strength", enemies[0])

    if npc.emotional_state.get("fearful", 0) > 0.6:
        # Fearful NPCs flee more readily
        return Action("flee", "dexterity")

    if goal.type == "attack":
        enemies = get_enemies(scene, npc)

        # Adjust behavior based on recent failures
        for m in reversed(memory):
            if m.get("action") == "attack" and m.get("outcome") == "failure":
                enemies = list(reversed(enemies))

        if enemies:
            target = enemies[0]
            return Action("attack", "strength", target)

    if goal.type == "survive":
        return Action("flee", "dexterity")

    if goal.type == "observe":
        return Action("scan", "intelligence")

    return Action("wait", "none")


def generate_npc_dialogue(npc, context, emotional_state):
    """
    Generate consistent character dialogue using LLM.
    """
    # Cache to avoid duplicate calls per turn
    if not hasattr(npc, '_dialogue_cache'):
        npc._dialogue_cache = {}

    cache_key = f"{context}_{emotional_state}"
    if cache_key in npc._dialogue_cache:
        return npc._dialogue_cache[cache_key]

    # LLM prompt
    prompt = f"""
    You are roleplaying a character.

    Personality: {npc.personality}
    Voice style: {npc.voice_style}
    Speaking patterns: {npc.speaking_patterns}
    Emotional state: {emotional_state}
    Context: {context}

    Generate one line of dialogue.
    """

    # Placeholder LLM call - in real implementation, call actual LLM
    dialogue = f"[{npc.voice_style}] {prompt.split('Generate one line')[0].strip()}"  # Mock

    npc._dialogue_cache[cache_key] = dialogue
    return dialogue