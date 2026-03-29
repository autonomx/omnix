"""
NPC Mind — LLM-driven cognitive simulation for NPCs.

Implements the NPC "mind stack" pipeline:

    Memory → Beliefs → Goals → GOAP Plan → LLM Interpretation → Action

Each NPC is a goal-driven agent with memory, beliefs, and strategy.
The LLM acts as a *reasoning layer* on top of structured state — it does
NOT directly mutate the world.  All actions pass through engine validation.

Key subsystems:
    - Belief system: subjective confidence scores updated from events
    - Memory summarisation: keeps LLM context within token limits
    - Deception: dual-state intent (true vs expressed)
    - Tiered intelligence: full LLM for nearby NPCs, GOAP-only for far
    - Multi-NPC belief propagation: rumours, misinformation
"""

import json
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Allowed NPC action types (LLM output validation)
ALLOWED_ACTIONS = frozenset({
    "attack", "flee", "trade", "help", "scheme", "guard",
    "confront", "talk", "deceive", "observe", "idle",
})

# Intelligence tiers
TIER_LLM = 1       # Full LLM reasoning (nearby / active NPCs)
TIER_GOAP = 2      # Simplified GOAP-only (medium distance)
TIER_SIM = 3       # Pure simulation (far away)

# Distance thresholds for tier assignment
_TIER_THRESHOLDS = {1: 2, 2: 5}  # tier 1 if dist < 2, tier 2 if dist < 5


# ── Belief System ──────────────────────────────────────────────────────────

def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def update_beliefs(npc: Dict[str, Any]) -> Dict[str, float]:
    """
    Update an NPC's beliefs from their recent memories and emotional state.

    Each memory event can nudge a belief's confidence score.  Beliefs are
    subjective — NPCs may hold *incorrect* beliefs.

    Returns the updated beliefs dict (also mutates *npc* in-place).
    """
    beliefs: Dict[str, float] = dict(npc.get("beliefs", {}))
    memories: List[Dict[str, Any]] = npc.get("memories", [])[-10:]
    opinions: Dict[str, int] = npc.get("opinions", {})

    for mem in memories:
        action = mem.get("action", "")
        actor = mem.get("actor", "")
        importance = mem.get("importance", 0.5)

        if actor == "player":
            if action in ("threaten", "attack"):
                beliefs["player_is_hostile"] = clamp(
                    beliefs.get("player_is_hostile", 0.5) + 0.3 * importance,
                )
            elif action in ("help", "gift", "heal"):
                beliefs["player_is_hostile"] = clamp(
                    beliefs.get("player_is_hostile", 0.5) - 0.4 * importance,
                )
                beliefs["player_is_ally"] = clamp(
                    beliefs.get("player_is_ally", 0.3) + 0.2 * importance,
                )
            elif action in ("steal", "lie"):
                beliefs["player_is_trustworthy"] = clamp(
                    beliefs.get("player_is_trustworthy", 0.5) - 0.3 * importance,
                )

    # Emotional reinforcement: high anger → raise hostile belief
    anger = npc.get("emotional_state", {}).get("anger", 0)
    if anger > 0.5:
        beliefs["world_is_dangerous"] = clamp(
            beliefs.get("world_is_dangerous", 0.3) + 0.1 * anger,
        )

    # Player opinion → trust belief
    player_opinion = opinions.get("player", 0)
    if player_opinion < -30:
        beliefs["player_is_hostile"] = clamp(
            beliefs.get("player_is_hostile", 0.5) + 0.1,
        )
    elif player_opinion > 30:
        beliefs["player_is_ally"] = clamp(
            beliefs.get("player_is_ally", 0.3) + 0.1,
        )

    npc["beliefs"] = beliefs
    return beliefs


# ── Memory Summarisation ──────────────────────────────────────────────────

def summarize_memory(npc: Dict[str, Any], max_entries: int = 5) -> str:
    """
    Build a concise narrative summary of an NPC's recent memories.

    This is the version sent to the LLM to keep token usage low.
    """
    memories = npc.get("memories", [])
    recent = memories[-max_entries:] if len(memories) > max_entries else memories

    if not recent:
        return "No significant memories."

    lines: List[str] = []
    for m in recent:
        actor = m.get("actor", "someone")
        action = m.get("action", "did something")
        importance = m.get("importance", 0.5)
        marker = "!" if importance > 0.7 else ""
        lines.append(f"- {actor} {action}{marker}")

    summary = "\n".join(lines)
    npc["memory_summary"] = summary
    return summary


# ── Memory Decay ──────────────────────────────────────────────────────────

def decay_memories(npc: Dict[str, Any], threshold: float = 0.2) -> None:
    """
    Remove low-importance, old memories to prevent memory bloat.

    Keeps recent memories (last 3) regardless of importance.
    """
    memories = npc.get("memories", [])
    if len(memories) <= 3:
        return

    recent = memories[-3:]
    older = memories[:-3]
    kept = [m for m in older if m.get("importance", 0.5) > threshold]
    npc["memories"] = kept + recent


# ── Goal Selection ────────────────────────────────────────────────────────

def select_goal(npc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Select the highest-priority active goal, dynamically adjusted by beliefs.

    Returns the goal dict or ``None`` if no goals exist.
    """
    goals = npc.get("active_goals", [])
    if not goals:
        return None

    beliefs = npc.get("beliefs", {})

    # Create working copies with adjusted priorities
    adjusted: List[Tuple[Dict[str, Any], float]] = []
    for goal in goals:
        priority = goal.get("priority", 0.5)

        # Beliefs can boost/suppress goal priorities
        goal_type = goal.get("type", "")
        if goal_type in ("defend", "survive") and beliefs.get("world_is_dangerous", 0) > 0.6:
            priority += 0.2
        if goal_type in ("defend", "confront") and beliefs.get("player_is_hostile", 0) > 0.7:
            priority += 0.15
        if goal_type in ("trade", "help") and beliefs.get("player_is_ally", 0) > 0.6:
            priority += 0.1

        adjusted.append((goal, clamp(priority, 0.0, 1.0)))

    if not adjusted:
        return None

    best = max(adjusted, key=lambda x: x[1])
    return best[0]


# ── Deception System ──────────────────────────────────────────────────────

def should_lie(npc: Dict[str, Any], context_risk: float = 0.5) -> bool:
    """
    Determine whether an NPC should lie based on honesty trait and context risk.

    Parameters
    ----------
    npc : dict
        NPC data dict.
    context_risk : float
        How risky it is for the NPC to tell the truth (0 = safe, 1 = dangerous).

    Returns
    -------
    bool
        ``True`` if the NPC decides to lie.
    """
    honesty = npc.get("personality_traits", {}).get("honest", 0.5)
    # Higher honesty + lower risk → less likely to lie
    threshold = honesty * (1.0 - context_risk)
    return random.random() > threshold


def build_expressed_state(npc: Dict[str, Any], context_risk: float = 0.5) -> Dict[str, str]:
    """
    Build the NPC's *expressed* state which may differ from their true intent.

    If the NPC decides to lie, their expressed intent/emotion diverge.
    """
    true_action = npc.get("current_action", "idle")
    true_emotion = max(
        npc.get("emotional_state", {"neutral": 0.5}).items(),
        key=lambda x: x[1],
        default=("neutral", 0.5),
    )

    if should_lie(npc, context_risk):
        # Distort: mask hostile intent, show friendliness
        distortion_map = {
            "attack": "talk",
            "confront": "observe",
            "scheme": "idle",
            "flee": "guard",
        }
        expressed_action = distortion_map.get(true_action, true_action)
        expressed_emotion = "calm" if true_emotion[0] in ("anger", "fear") else true_emotion[0]
    else:
        expressed_action = true_action
        expressed_emotion = true_emotion[0]

    expressed = {
        "intent": expressed_action,
        "emotion": expressed_emotion,
    }
    npc["expressed_state"] = expressed
    return expressed


# ── Tiered Intelligence ───────────────────────────────────────────────────

def get_intelligence_tier(
    npc_location: str,
    player_location: str,
    location_distances: Optional[Dict[str, Dict[str, int]]] = None,
) -> int:
    """
    Determine the intelligence tier for an NPC based on distance to player.

    Tier 1: Full LLM reasoning (nearby / same location)
    Tier 2: GOAP-only reasoning (medium distance)
    Tier 3: Pure simulation (far away)
    """
    if npc_location == player_location:
        return TIER_LLM

    if location_distances:
        dist = location_distances.get(npc_location, {}).get(player_location, 99)
    else:
        # No distance data — if same location name, tier 1; else tier 3
        dist = 0 if npc_location == player_location else 99

    for tier, threshold in sorted(_TIER_THRESHOLDS.items()):
        if dist < threshold:
            return tier

    return TIER_SIM


# ── Multi-NPC Belief Propagation ──────────────────────────────────────────

def propagate_beliefs(
    source_npc: Dict[str, Any],
    target_npc: Dict[str, Any],
    trust_threshold: int = 10,
) -> bool:
    """
    Propagate beliefs from *source_npc* to *target_npc* if trust is sufficient.

    Only beliefs held with confidence > 0.6 are propagated, and they transfer
    at reduced confidence (× 0.5).  This enables rumours and misinformation.

    Returns ``True`` if any beliefs were propagated.
    """
    source_name = source_npc.get("name", "")
    target_opinions = target_npc.get("opinions", {})

    # Target must have a positive enough opinion of source
    if target_opinions.get(source_name, 0) < trust_threshold:
        return False

    source_beliefs = source_npc.get("beliefs", {})
    target_beliefs = dict(target_npc.get("beliefs", {}))
    propagated = False

    for belief_key, confidence in source_beliefs.items():
        if confidence > 0.6:
            # Transfer at reduced confidence (rumour effect)
            new_confidence = clamp(
                target_beliefs.get(belief_key, 0.5) + (confidence - 0.5) * 0.5,
            )
            if abs(new_confidence - target_beliefs.get(belief_key, 0.5)) > 0.01:
                target_beliefs[belief_key] = new_confidence
                propagated = True

    if propagated:
        target_npc["beliefs"] = target_beliefs

    return propagated


# ── LLM Prompt Builder ───────────────────────────────────────────────────

def build_npc_prompt(
    npc: Dict[str, Any],
    plan: List[str],
    player_input: str = "",
    world_context: str = "",
) -> Tuple[str, str]:
    """
    Build the system prompt and user prompt for an NPC's LLM decision call.

    Returns (system_prompt, user_prompt).
    """
    name = npc.get("name", "Unknown NPC")
    role = npc.get("role", "villager")
    traits = npc.get("personality_traits", {})
    beliefs = npc.get("beliefs", {})
    memory_summary = npc.get("memory_summary", "No significant memories.")
    expressed = npc.get("expressed_state", {})

    # Build per-NPC system prompt using llm_profile or defaults
    profile = npc.get("llm_profile", {})
    style = profile.get("style", "neutral")
    custom_system = profile.get("system_prompt", "")

    if custom_system:
        system_prompt = custom_system
    else:
        traits_str = ", ".join(f"{k}: {v:.1f}" for k, v in traits.items()) or "none"
        beliefs_str = ", ".join(f"{k}: {v:.2f}" for k, v in beliefs.items()) or "none"

        system_prompt = (
            f"You are {name}, a {role}.\n\n"
            f"Personality traits: {traits_str}\n"
            f"Beliefs: {beliefs_str}\n"
            f"Style: {style}\n\n"
            "Rules:\n"
            "- You may lie if your honesty trait is low and it benefits you\n"
            "- You do not reveal secrets easily\n"
            "- Your actions must be consistent with your personality\n\n"
            "Respond with ONLY valid JSON:\n"
            '{"action": "...", "dialogue": "...", "intent": "...", "emotion": "..."}\n'
            "action must be one of: attack, flee, trade, help, scheme, guard, "
            "confront, talk, deceive, observe, idle"
        )

    # Build user prompt
    plan_str = ", ".join(plan) if plan else "no specific plan"
    user_prompt = (
        f"Recent memories:\n{memory_summary}\n\n"
        f"Current goal plan: {plan_str}\n"
    )
    if world_context:
        user_prompt += f"\nWorld context: {world_context}\n"
    if player_input:
        user_prompt += f"\nPlayer action: {player_input}\n"
    user_prompt += "\nDecide what to do. Respond with ONLY valid JSON."

    return system_prompt, user_prompt


# ── LLM Output Validation ────────────────────────────────────────────────

def validate_npc_action(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitise an LLM-generated NPC action.

    Ensures the action is in the allowed set; falls back to "idle" if not.
    Returns a cleaned action dict with guaranteed keys.
    """
    action = result.get("action", "idle")
    if action not in ALLOWED_ACTIONS:
        logger.warning("Invalid NPC action '%s' — falling back to idle", action)
        action = "idle"

    return {
        "action": action,
        "dialogue": str(result.get("dialogue", ""))[:500],  # cap length
        "intent": str(result.get("intent", action))[:100],
        "emotion": str(result.get("emotion", "neutral"))[:50],
    }


# ── GOAP-only Fallback ───────────────────────────────────────────────────

def goap_decide(npc: Dict[str, Any], world_context: str = "") -> Dict[str, Any]:
    """
    Simple GOAP-style decision for tier 2+ NPCs (no LLM call).

    Uses the existing npc_decision engine as the planner and wraps the
    result in the standard action format.
    """
    from app.rpg.npc_decision import decide_npc_action

    decision = decide_npc_action(npc)
    intent = decision.get("intent", "idle")

    return {
        "action": intent,
        "dialogue": "",
        "intent": intent,
        "emotion": "neutral",
    }


# ── Full NPC Think Pipeline ──────────────────────────────────────────────

def npc_think(
    npc: Dict[str, Any],
    player_input: str = "",
    player_location: str = "",
    world_context: str = "",
    location_distances: Optional[Dict[str, Dict[str, int]]] = None,
    llm_call_fn: Optional[Any] = None,
    parse_json_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Full NPC mind pipeline:

        Memory → Beliefs → Goals → GOAP Plan → LLM Interpretation → Action

    Parameters
    ----------
    npc : dict
        NPC data (as from ``NPCCharacter.to_dict()``).
    player_input : str
        What the player just did/said.
    player_location : str
        Player's current location.
    world_context : str
        Summary of world state for LLM context.
    location_distances : dict, optional
        Distance matrix between locations for tiering.
    llm_call_fn : callable, optional
        ``(system_prompt, user_prompt) → str`` for LLM calls.
        If ``None``, falls back to GOAP-only.
    parse_json_fn : callable, optional
        ``(text) → dict`` for parsing LLM JSON output.

    Returns
    -------
    dict
        ``{"action", "dialogue", "intent", "emotion"}``
    """
    # 1. Decay old unimportant memories
    decay_memories(npc)

    # 2. Update beliefs from memories + emotions
    update_beliefs(npc)

    # 3. Summarise memory for LLM context
    summarize_memory(npc)

    # 4. Build expressed state (deception layer)
    npc_location = npc.get("location", "")
    context_risk = 0.5
    beliefs = npc.get("beliefs", {})
    if beliefs.get("player_is_hostile", 0) > 0.6:
        context_risk = 0.8
    build_expressed_state(npc, context_risk)

    # 5. Select highest-priority goal
    goal = select_goal(npc)
    plan = [goal.get("type", "idle")] if goal else ["idle"]

    # 6. Determine intelligence tier
    tier = get_intelligence_tier(npc_location, player_location, location_distances)

    # 7. Tier 2+: GOAP-only (no LLM call)
    if tier >= TIER_GOAP or llm_call_fn is None:
        return goap_decide(npc, world_context)

    # 8. Tier 1: Full LLM reasoning
    system_prompt, user_prompt = build_npc_prompt(
        npc, plan, player_input, world_context,
    )

    raw_response = llm_call_fn(system_prompt, user_prompt)
    if not raw_response:
        return goap_decide(npc, world_context)

    if parse_json_fn:
        parsed = parse_json_fn(raw_response)
    else:
        try:
            parsed = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError):
            parsed = None

    if not parsed or not isinstance(parsed, dict):
        logger.warning("NPC %s: LLM returned unparseable response, falling back to GOAP",
                       npc.get("name", "?"))
        return goap_decide(npc, world_context)

    # 9. Validate LLM output strictly
    return validate_npc_action(parsed)
