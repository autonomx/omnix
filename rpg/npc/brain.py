from rpg.models.npc import NPC
from rpg.actions.resolution import Action
from rpg.scene.scene import get_enemies
from rpg.npc.goals import select_goal
from rpg.memory.memory import retrieve_relevant

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