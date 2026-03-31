"""
NPC Brain — utility-based scoring system for NPC decision-making.

Replaces simple if/else decisions with a weighted scoring approach that
considers personality traits, emotional state, needs, faction ideology,
memories, and inter-NPC relationships.  This produces more nuanced and
emergent NPC behaviour.
"""

from typing import Any, Dict, List, Tuple

# All actions an NPC can consider
ACTIONS = ["attack", "flee", "trade", "help", "scheme", "guard", "idle"]


def score_action(
    npc: Dict[str, Any],
    action: str,
    context: Dict[str, Any],
) -> float:
    """
    Calculate a utility score for *action* given NPC state and context.

    Higher scores mean the NPC is more inclined to perform the action.
    Factors considered:

    * personality traits (aggressive, greedy, loyal, kind, bravery, ambition)
    * emotional state (anger, fear, trust)
    * needs (wealth, safety, power)
    * opinions of the player and other NPCs
    * faction ideology (if provided in context)
    * recent memories (emotional weighting)
    """
    score = 0.0

    traits = npc.get("personality_traits", {})
    emotions = npc.get("emotional_state", {})
    needs = npc.get("needs", {})
    opinions = npc.get("opinions", {})

    # --- Base behaviour scoring -------------------------------------------
    if action == "attack":
        score += traits.get("aggressive", 0) * 2
        score += emotions.get("anger", 0) * 3
        score -= emotions.get("fear", 0) * 2
        score += needs.get("power", 0)

    elif action == "flee":
        score += emotions.get("fear", 0) * 3
        score -= traits.get("bravery", 0) * 2
        score += needs.get("safety", 0)

    elif action == "trade":
        score += needs.get("wealth", 0) * 2
        score += traits.get("greedy", 0)
        score += emotions.get("trust", 0)

    elif action == "help":
        score += traits.get("kind", 0) * 2
        score += traits.get("loyal", 0)
        score += opinions.get("player", 0) * 0.03  # scale ±100 → ±3

    elif action == "scheme":
        score += traits.get("ambition", 0) * 2
        score += needs.get("power", 0) * 2
        score -= traits.get("loyal", 0)

    elif action == "guard":
        score += traits.get("loyal", 0) * 2
        score += needs.get("safety", 0)
        score -= emotions.get("fear", 0)

    elif action == "idle":
        score += 0.1  # tiny baseline so it always appears

    # --- Faction ideology influence ----------------------------------------
    faction = context.get("faction", {})
    if faction:
        ideology = faction.get("ideology", {})
        if action == "attack":
            score += ideology.get("violence", 0)
        if action == "trade":
            score += ideology.get("commerce", 0)
        if action == "scheme":
            score += ideology.get("ambition", 0)
        if action == "help":
            score += ideology.get("altruism", 0)

    # --- NPC→NPC rivalry / alliance pressure --------------------------------
    for other_name, opinion in opinions.items():
        if other_name == "player":
            continue
        if opinion < -5:
            if action == "attack":
                score += 1.0
            if action == "scheme":
                score += 0.5
        elif opinion > 5:
            if action == "help":
                score += 0.5

    # --- Memory weighting (recent emotional experiences) -------------------
    recent_memories = npc.get("memories", [])[-5:]
    for m in recent_memories:
        emotion = m.get("emotion", "")
        intensity = m.get("intensity", 0)
        if emotion == "anger" and action == "attack":
            score += intensity * 0.5
        elif emotion == "fear" and action == "flee":
            score += intensity * 0.5
        elif emotion == "trust" and action == "help":
            score += intensity * 0.3
        elif emotion == "greed" and action == "trade":
            score += intensity * 0.3

    return score


def decide_action(
    npc: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Select the best action for an NPC using utility scoring.

    Returns ``{"intent": str, "score": float}``.
    """
    best_action = "idle"
    best_score = -999.0

    for action in ACTIONS:
        s = score_action(npc, action, context)
        if s > best_score:
            best_score = s
            best_action = action

    return {"intent": best_action, "score": round(best_score, 3)}


def evaluate_npc_interactions(
    npcs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Detect NPC→NPC conflicts or alliances based on opinions.

    Returns a list of interaction dicts:
    ``{"source": str, "target": str, "type": "conflict"|"alliance"}``
    """
    interactions: List[Dict[str, Any]] = []
    seen = set()

    for npc in npcs:
        name = npc.get("name", "")
        for other_name, opinion in npc.get("opinions", {}).items():
            if other_name == "player":
                continue
            pair = tuple(sorted((name, other_name)))
            if pair in seen:
                continue
            seen.add(pair)

            if opinion < -5:
                interactions.append({
                    "source": name,
                    "target": other_name,
                    "type": "conflict",
                })
            elif opinion > 5:
                interactions.append({
                    "source": name,
                    "target": other_name,
                    "type": "alliance",
                })

    return interactions
