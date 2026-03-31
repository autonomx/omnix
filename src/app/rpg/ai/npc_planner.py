from rpg.ai.goap import Action, GOAPPlanner


def build_actions(npc, session):
    return [
        Action(
            "attack",
            {"enemy_visible": True},
            {"enemy_alive": False},
            cost=2
        ),
        Action(
            "flee",
            {"low_hp": True},
            {"safe": True},
            cost=1
        ),
        Action(
            "idle",
            {},
            {},
            cost=0
        )
    ]


def build_state(npc):
    return {
        "low_hp": npc.hp < 30,
        "enemy_visible": True,
        "enemy_alive": True,
        "angry": npc.emotional_state.get("mood") == "angry",
        "has_target": npc.goal is not None
    }


def build_goal(npc):
    if npc.hp < 30:
        return {"safe": True}

    if npc.emotional_state.get("mood") == "angry":
        return {"enemy_alive": False}

    return {"enemy_alive": False}


def update_npc_emotions(npc):
    anger = npc.emotional_state.get("anger", 0)

    for e in npc.memory[-5:]:
        if e["type"] == "damage" and e["target"] == npc.id:
            anger += 2

    # decay
    anger = max(0, min(10, anger - 0.5))

    npc.emotional_state["anger"] = anger
    npc.emotional_state["mood"] = "angry" if anger > 3 else "neutral"


def choose_target(npc, session):
    recent = [e for e in npc.memory if e["type"] == "damage"]

    if recent:
        return recent[-1]["actor"]

    return "player"


def decide(npc, session):
    update_npc_emotions(npc)

    planner = GOAPPlanner()

    state = build_state(npc)
    goal = build_goal(npc)
    actions = build_actions(npc, session)

    plan = planner.plan(state, goal, actions)

    if not plan:
        return {"action": "idle"}

    return {"action": plan[0].name}