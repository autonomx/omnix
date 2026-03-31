from rpg.models.npc import NPC
from rpg.scene.scene import has_enemy


class Goal:
    def __init__(self, type: str, priority: int, target=None):
        self.type = type
        self.priority = priority
        self.target = target

def select_goal(npc: NPC, scene):
    scored_goals = []

    for goal in npc.goals:
        score = goal.priority

        # Context modifiers
        if goal.type == "survive" and npc.hp < 30:
            score += 10

        if goal.type == "attack" and has_enemy(scene, npc):
            score += 5

        scored_goals.append((goal, score))

    scored_goals.sort(key=lambda x: x[1], reverse=True)

    if not scored_goals:
        default_goal = Goal("wait", 0)
        npc.current_goal = default_goal
        return default_goal

    npc.current_goal = scored_goals[0][0]
    return npc.current_goal