"""
NPC Decision Engine — deterministic decision layer for NPC behaviour.

Evaluates an NPC's emotional state, opinions, personality traits, and needs
to determine what action the NPC would take *before* the LLM refines the
narrative.  This keeps NPC behaviour consistent and emotion-driven.
"""

from typing import Any, Dict, List, Optional, Tuple


def decide_npc_action(
    npc_dict: Dict[str, Any],
    player_location: str = "",
    player_wealth: int = 0,
) -> Dict[str, Any]:
    """
    Deterministic decision layer for a single NPC.

    Uses emotional state, opinions, personality traits, and needs to pick
    an action intent.  Returns a dict with ``intent`` (str) and ``weight``
    (float, 0-1 indicating urgency).

    Parameters
    ----------
    npc_dict : dict
        NPC data (as produced by ``NPCCharacter.to_dict()``).
    player_location : str
        Current player location for proximity-aware decisions.
    player_wealth : int
        Player wealth for trade-related decisions.

    Returns
    -------
    dict
        ``{"intent": str, "weight": float}``
    """
    emotional_state = npc_dict.get("emotional_state", {})
    opinions = npc_dict.get("opinions", {})
    personality = npc_dict.get("personality_traits", {})
    needs = npc_dict.get("needs", {})
    npc_location = npc_dict.get("location", "")

    anger = emotional_state.get("anger", 0.0)
    fear = emotional_state.get("fear", 0.0)
    trust = emotional_state.get("trust", 0.0)

    player_opinion = opinions.get("player", 0)

    aggression = personality.get("aggressive", 0.0)
    greed = personality.get("greedy", 0.0)
    loyalty = personality.get("loyal", 0.0)

    wealth_need = needs.get("wealth", 0.0)
    safety_need = needs.get("safety", 0.0)
    power_need = needs.get("power", 0.0)

    # --- Score candidate actions -------------------------------------------
    scores: List[Tuple[str, float]] = []

    # Confront / attack — driven by anger + aggression
    confront_score = anger * 0.5 + aggression * 0.4 + power_need * 0.1
    if confront_score > 0.5:
        scores.append(("confront", min(confront_score, 1.0)))

    # Flee — driven by fear + low aggression
    flee_score = fear * 0.6 + safety_need * 0.3 - aggression * 0.2
    if flee_score > 0.4:
        scores.append(("flee", min(flee_score, 1.0)))

    # Trade — driven by greed + wealth need (only if player has wealth)
    if player_wealth > 0:
        trade_score = greed * 0.4 + wealth_need * 0.4 + trust * 0.2
        if trade_score > 0.3:
            scores.append(("trade", min(trade_score, 1.0)))

    # Help — driven by trust + loyalty + positive opinion
    help_score = trust * 0.3 + loyalty * 0.3 + (player_opinion / 100.0) * 0.4
    if help_score > 0.3:
        scores.append(("help", min(help_score, 1.0)))

    # Guard / patrol — driven by loyalty + safety need
    guard_score = loyalty * 0.4 + safety_need * 0.4 + (1 - fear) * 0.2
    if guard_score > 0.5:
        scores.append(("guard", min(guard_score, 1.0)))

    # Scheme — driven by greed + power need + low loyalty
    scheme_score = greed * 0.3 + power_need * 0.4 + (1 - loyalty) * 0.3
    if scheme_score > 0.5:
        scores.append(("scheme", min(scheme_score, 1.0)))

    # --- Pick highest-scoring action or default to idle --------------------
    if not scores:
        return {"intent": "idle", "weight": 0.1}

    best = max(scores, key=lambda x: x[1])
    return {"intent": best[0], "weight": round(best[1], 3)}


def decide_all_npcs(
    npcs: List[Dict[str, Any]],
    player_location: str = "",
    player_wealth: int = 0,
) -> List[Dict[str, Any]]:
    """
    Run the decision engine on every NPC and return a list of decisions.

    Each entry includes ``name``, ``intent``, and ``weight``.
    """
    decisions: List[Dict[str, Any]] = []
    for npc in npcs:
        decision = decide_npc_action(npc, player_location, player_wealth)
        decisions.append({
            "name": npc.get("name", "Unknown"),
            **decision,
        })
    return decisions
