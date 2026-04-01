import random

from rpg.ai.goap import Action, GOAPPlanner
from rpg.spatial import distance, astar
from rpg.emotion import decay_emotions
from rpg.simulation import find_npc


def move_toward(npc, session):
    """Move NPC toward target using A* pathfinding with obstacle avoidance."""
    target_id = npc.emotional_state.get("top_threat")
    target = find_npc(session, target_id)

    if not target:
        return

    path = astar(npc.position, target.position, session)

    if len(path) > 1:
        npc.position = path[1]


def build_actions(npc, session):
    return [
        Action(
            "attack",
            {"enemy_visible": True, "in_range": True},
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
            "wander",
            {},
            {},
            cost=0
        ),
        Action(
            "observe",
            {},
            {},
            cost=0
        ),
        Action(
            "move_toward",
            {"has_target": True},
            {"enemy_visible": True},
            cost=1,
        )
    ]


def build_state(npc, session):
    decay_emotions(npc, session.world.time)

    target_id = npc.emotional_state.get("top_threat")
    target = find_npc(session, target_id)

    in_range = target and distance(npc.position, target.position) <= 1

    return {
        "low_hp": npc.hp < 30,
        "enemy_visible": target is not None,
        "enemy_alive": target is not None and target.is_active,
        "in_range": in_range,
        "angry": npc.emotional_state["anger"] > 1.5,
        "afraid": npc.emotional_state["fear"] > 1.5,
        "has_target": target is not None
    }


def build_goal(npc):
    if npc.hp < 30:
        return {"safe": True}

    if npc.emotional_state["anger"] > 1.5:
        return {"enemy_alive": False}

    return {"enemy_alive": False}


def update_npc_emotions(npc):
    """Update NPC emotions with anger tracking based on recent damage events."""
    anger_map = npc.emotional_state.get("anger_map", {})

    for e in npc.memory[-5:]:
        if e["type"] == "damage" and e["target"] == npc.id:
            src = e.get("source") or e.get("actor")
            if src:
                # Weight by recency: newer events have higher weight
                age = npc.session.world.time - e.get("tick", 0)
                weight = max(0.5, 2 - age * 0.2)
                anger_map[src] = anger_map.get(src, 0) + weight

    # Decay all anger values
    for k in list(anger_map.keys()):
        anger_map[k] = max(0, anger_map[k] - 0.5)
        if anger_map[k] == 0:
            del anger_map[k]

    npc.emotional_state["anger_map"] = anger_map
    npc.emotional_state["top_threat"] = max(anger_map, key=anger_map.get) if anger_map else None

    # Derive mood from continuous emotional state
    npc.emotional_state["mood"] = "angry" if npc.emotional_state["anger"] > 1.5 else "calm"


def choose_target(npc, session):
    """Choose attack target based on anger map with distance weighting.

    Includes stabilization to prevent target flicker between turns.
    """
    anger_map = npc.emotional_state.get("anger_map", {})

    # Stabilize: prefer current top_threat if still valid
    current_target = npc.emotional_state.get("top_threat")
    if current_target and current_target in anger_map:
        target = find_npc(session, current_target)
        if target and target.is_active:
            return current_target

    if not anger_map:
        return "player"

    candidates = []
    for target_id, anger in anger_map.items():
        target = find_npc(session, target_id)
        if not target or not target.is_active:
            continue

        dist = distance(npc.position, target.position)
        score = anger - dist * 0.5
        candidates.append((score, target_id))

    if not candidates:
        return "player"

    return max(candidates)[1]


def decide(npc, session):
    update_npc_emotions(npc)

    planner = GOAPPlanner()

    state = build_state(npc, session)
    goal = build_goal(npc)
    actions = build_actions(npc, session)

    plan = planner.plan(state, goal, actions)

    if not plan:
        # Default idle behavior: wander or observe to avoid frozen NPCs
        # Add jitter prevention: if last action was move and position didn't change, idle
        if npc.memory and npc.memory[-1].get("action") == "move":
            if npc.memory[-1].get("pos") == npc.position:
                return {"action": "idle"}
        return {"action": random.choice(["wander", "observe"])}

    return {"action": plan[0].name}