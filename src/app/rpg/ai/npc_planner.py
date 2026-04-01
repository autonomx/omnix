import random

from rpg.ai.goap import Action
from rpg.ai.goap.planner import plan as goap_plan
from rpg.ai.goap.actions import default_actions as goap_default_actions
from rpg.ai.goap.state_builder import build_world_state, select_goal
from rpg.ai.memory_context import build_memory_context, summarize_relationships
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


def build_decision_context(npc, session):
    """
    Build rich context for memory retrieval.
    This is CRITICAL for relevant memory recall.
    """
    top_threat = npc.emotional_state.get("top_threat")
    anger = npc.emotional_state.get("anger", 0)

    # Infer intent
    if npc.hp < 30:
        intent = "survive"
    elif anger > 1.5:
        intent = "attack"
    else:
        intent = "explore"

    return {
        "type": "decision",
        "source": npc.id,
        "target": top_threat,
        "location": npc.position,
        "intent": intent,
    }


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
    """Decide NPC action using GOAP with plan persistence and narrative mandates.
    
    Plan Persistence: NPCs don't replan every tick unless the world changes
    significantly. This gives continuity and believable intent.
    
    Mandated Goals: Story arcs in tension/climax phases can force specific goals.
    
    Args:
        npc: The NPC deciding on an action.
        session: The current game session.
        
    Returns:
        Dict with decided action and metadata.
    """
    update_npc_emotions(npc)

    # Build rich context for memory retrieval
    current_context = build_decision_context(npc, session)

    npc.emotional_state["memory_context"] = build_memory_context(
        npc,
        current_context,
        session
    )
    
    # Get relationship summaries for better decision making
    relationships = summarize_relationships(npc, session)
    npc.emotional_state["relationships"] = relationships

    # 🔥 PLAN PERSISTENCE — Only replan if conditions changed
    if hasattr(npc, '_current_plan') and npc._current_plan:
        # Check if we should continue current plan
        if not _world_changed_significantly(npc, session, state=None):
            next_action, remaining_plan = npc._current_plan[0], npc._current_plan[1:]
            npc._current_plan = remaining_plan
            
            # 🔥 Spatial reasoning — handle move_to_target
            if next_action == "move_to_target":
                target_id = npc.emotional_state.get("top_threat")
                if target_id:
                    return {
                        "action": "move_toward",
                        "target_id": target_id,
                        "plan": [next_action] + remaining_plan,
                        "goal": npc._current_goal if hasattr(npc, '_current_goal') else {}
                    }
            
            return {
                "action": next_action,
                "plan": [next_action] + remaining_plan,
                "goal": npc._current_goal if hasattr(npc, '_current_goal') else {}
            }

    # Build world state and select goal (checks mandated goals via Story Director)
    state = build_world_state(npc, session)
    goal = select_goal(npc, session)
    actions = goap_default_actions()

    plan_result = goap_plan(state, goal, actions)

    if not plan_result:
        # Default idle behavior: wander or observe to avoid frozen NPCs
        # Add jitter prevention: if last action was move and position didn't change, idle
        
        # Check memory for last action (support both list and dict memory)
        memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else npc.memory
        if memories and memories[-1].get("action") == "move":
            if memories[-1].get("pos") == npc.position:
                return {"action": "idle"}
        
        # Clear stale plan
        npc._current_plan = None
        return {"action": random.choice(["wander", "observe"])}

    next_action = plan_result[0].name
    
    # Store plan for persistence
    npc._current_plan = [a.name for a in plan_result[1:]]  # Remaining steps
    npc._current_goal = goal

    # 🔥 Spatial reasoning — handle move_to_target specially
    if next_action == "move_to_target":
        target_id = state.get("target_id") or npc.emotional_state.get("top_threat")
        if target_id:
            target = find_npc(session, target_id)
            if target:
                # Execute movement to close distance
                return {
                    "action": "move_toward",
                    "target_id": target_id,
                    "plan": [a.name for a in plan_result],
                    "goal": goal
                }

    return {
        "action": next_action,
        "plan": [a.name for a in plan_result],
        "goal": goal
    }


def _world_changed_significantly(npc, session, state=None):
    """Check if the world has changed enough to warrant replanning.
    
    Args:
        npc: The NPC to check.
        session: The game session.
        state: Current world state (optional, will build if None).
        
    Returns:
        True if significant change occurred.
    """
    if not hasattr(npc, '_last_plan_state'):
        return True
        
    last = npc._last_plan_state
    current = {
        "hp_low": npc.hp < 30,
        "hp": npc.hp,
        "target": npc.emotional_state.get("top_threat"),
    }
    
    # Major HP change
    if abs(current.get("hp", 100) - last.get("hp", 100)) > 20:
        return True
        
    # Target changed
    if current.get("target") != last.get("target"):
        if current.get("target") and last.get("target"):
            return True  # Different target detected
            
    return False
