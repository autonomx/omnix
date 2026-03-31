from rpg.models.npc import NPC
from rpg.actions.resolution import Action
from rpg.scene.scene import get_enemies
from rpg.npc.goals import select_goal
from rpg.memory.memory import retrieve_relevant

def npc_decide(npc: NPC, scene):
    memory = retrieve_relevant(npc, scene)
    goal = select_goal(npc, scene)
    action = decide_action(npc, goal, scene)
    return action

def decide_action(npc: NPC, goal, scene):
    if goal.type == "attack":
        enemies = get_enemies(scene, npc)
        if enemies:
            target = enemies[0]
            return Action("attack", "strength", target)

    if goal.type == "survive":
        return Action("flee", "dexterity")

    return Action("wait", "none")