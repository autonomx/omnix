import random

from rpg.models.npc import NPC


class Action:
    def __init__(self, type: str, stat: str, target=None):
        self.type = type
        self.stat = stat
        self.target = target

def get_stat_modifier(actor: NPC, stat: str):
    return (actor.stats.get(stat, 10) - 10) // 2

def resolve_action(actor: NPC, action: Action, difficulty: int):
    roll = random.randint(1, 20)

    stat_mod = get_stat_modifier(actor, action.stat)

    total = roll + stat_mod

    if total >= difficulty + 5:
        return "critical_success"
    elif total >= difficulty:
        return "success"
    elif total >= difficulty - 5:
        return "partial_success"
    else:
        return "failure"