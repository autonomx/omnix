"""
NPC Mind — LLM-driven cognitive simulation for NPCs.

Implements the NPC "mind stack" pipeline:

    Memory → Beliefs → Goals → GOAP Plan → LLM Interpretation → Action

Each NPC is a goal-driven agent with memory, beliefs, and strategy.
The LLM acts as a *reasoning layer* on top of structured state — it does
NOT directly mutate the world.  All actions pass through engine validation.

Key subsystems:
    - Causal belief system: beliefs derived from weighted sources
    - Emotional memory: memories carry emotion tags and intensity
    - Deception strategies: conceal / distort / fabricate / signal
    - Theory of mind: NPCs model what others believe
    - Personality evolution: traits shift based on actions
    - LLM plan override: strategic deviation from GOAP
    - Tiered intelligence: full LLM for nearby NPCs, GOAP-only for far
    - Multi-NPC belief propagation: rumours, misinformation
    - World event memory: global events feed into NPC awareness
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

# Valid deception modes
DECEPTION_MODES = frozenset({"none", "conceal", "distort", "fabricate", "signal"})


# ── Utilities ─────────────────────────────────────────────────────────────

def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


# ── Causal Belief System ──────────────────────────────────────────────────

def recompute_belief(npc: Dict[str, Any], key: str) -> float:
    """
    Recompute a single belief from its causal sources.

    Beliefs are the *sum* of weighted source contributions, clamped to [0, 1].
    Sources include memories, rumours, emotional state, and direct evidence.
    """
    sources = npc.get("belief_sources", {}).get(key, [])
    if not sources:
        return npc.get("beliefs", {}).get(key, 0.5)
    return clamp(sum(s.get("weight", 0) for s in sources))


def add_belief_source(
    npc: Dict[str, Any],
    belief_key: str,
    source: str,
    weight: float,
) -> None:
    """Add or update a source for a belief, then recompute."""
    belief_sources = npc.setdefault("belief_sources", {})
    sources = belief_sources.setdefault(belief_key, [])

    # Update existing source or append new one
    for s in sources:
        if s.get("source") == source:
            s["weight"] = weight
            break
    else:
        sources.append({"source": source, "weight": weight})

    # Recompute the belief value
    npc.setdefault("beliefs", {})[belief_key] = recompute_belief(npc, belief_key)


def update_beliefs(npc: Dict[str, Any]) -> Dict[str, float]:
    """
    Update an NPC's beliefs from their recent memories and emotional state.

    Uses the causal belief graph: each evidence source contributes a weighted
    amount to the final belief score.  This allows NPCs to justify, contradict,
    and be manipulated on their beliefs.

    Returns the updated beliefs dict (also mutates *npc* in-place).
    """
    beliefs: Dict[str, float] = dict(npc.get("beliefs", {}))
    memories: List[Dict[str, Any]] = npc.get("memories", [])[-10:]
    opinions: Dict[str, int] = npc.get("opinions", {})

    for mem in memories:
        action = mem.get("action", "")
        actor = mem.get("actor", "")
        importance = mem.get("importance", 0.5)
        emotion = mem.get("emotion", "")
        intensity = mem.get("intensity", 0.0)

        if actor == "player":
            if action in ("threaten", "attack"):
                add_belief_source(npc, "player_is_hostile",
                                  f"memory:{action}", 0.3 * importance)
            elif action in ("help", "gift", "heal"):
                add_belief_source(npc, "player_is_hostile",
                                  f"memory:{action}", -0.2 * importance)
                add_belief_source(npc, "player_is_ally",
                                  f"memory:{action}", 0.2 * importance)
            elif action in ("steal", "lie"):
                add_belief_source(npc, "player_is_trustworthy",
                                  f"memory:{action}", -0.3 * importance)

        # Emotional memory influence on beliefs
        if emotion == "fear" and intensity > 0.3:
            add_belief_source(npc, "world_is_dangerous",
                              f"emotion:fear:{actor}", 0.15 * intensity)
        elif emotion == "anger" and intensity > 0.3:
            add_belief_source(npc, "player_is_hostile",
                              f"emotion:anger:{actor}", 0.1 * intensity)
        elif emotion == "trust" and intensity > 0.3:
            add_belief_source(npc, "player_is_ally",
                              f"emotion:trust:{actor}", 0.1 * intensity)

    # Emotional reinforcement: high anger → raise hostile belief
    anger = npc.get("emotional_state", {}).get("anger", 0)
    if anger > 0.5:
        add_belief_source(npc, "world_is_dangerous",
                          "emotion:anger_state", 0.1 * anger)

    # Player opinion → trust belief
    player_opinion = opinions.get("player", 0)
    if player_opinion < -30:
        add_belief_source(npc, "player_is_hostile",
                          "opinion:player_negative", 0.1)
    elif player_opinion > 30:
        add_belief_source(npc, "player_is_ally",
                          "opinion:player_positive", 0.1)

    npc["beliefs"] = npc.get("beliefs", beliefs)
    return npc["beliefs"]


# ── Memory Summarisation ──────────────────────────────────────────────────

def summarize_memory(npc: Dict[str, Any], max_entries: int = 5) -> str:
    """
    Build a concise narrative summary of an NPC's recent memories.

    Includes emotional tags when present, keeping token usage low.
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
        emotion = m.get("emotion", "")
        intensity = m.get("intensity", 0.0)
        marker = "!" if importance > 0.7 else ""
        emotion_tag = f" [felt {emotion} ({intensity:.1f})]" if emotion and intensity > 0.3 else ""
        lines.append(f"- {actor} {action}{marker}{emotion_tag}")

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


# ── Deception Strategy System ─────────────────────────────────────────────

def select_deception_strategy(npc: Dict[str, Any], context_risk: float = 0.5) -> str:
    """
    Select an appropriate deception strategy based on personality and context.

    Modes:
      none     — honest
      conceal  — hide truth (omit information)
      distort  — twist truth (partial lies)
      fabricate — invent fiction (full lies)
      signal   — intentionally reveal hidden info (calculated honesty)

    Returns one of the DECEPTION_MODES strings.
    """
    honesty = npc.get("personality_traits", {}).get("honest", 0.5)
    aggression = npc.get("personality_traits", {}).get("aggressive", 0.3)
    intelligence = npc.get("personality_traits", {}).get("intelligent", 0.5)
    beliefs = npc.get("beliefs", {})
    player_hostile = beliefs.get("player_is_hostile", 0)

    # High honesty + low risk → no deception
    if honesty > 0.7 and context_risk < 0.3:
        return "none"

    # Strategic reveal: if NPC wants player to act on info
    if context_risk < 0.2 and intelligence > 0.6:
        return "signal"

    # High risk + low honesty → more extreme deception
    deception_drive = (1.0 - honesty) * context_risk

    if deception_drive > 0.6:
        return "fabricate" if intelligence > 0.5 else "distort"
    elif deception_drive > 0.3:
        return "distort" if aggression > 0.5 else "conceal"
    elif deception_drive > 0.1:
        return "conceal"

    return "none"


def should_lie(npc: Dict[str, Any], context_risk: float = 0.5) -> bool:
    """
    Determine whether an NPC should lie based on honesty trait and context risk.

    Backward-compatible wrapper around the deception strategy system.
    """
    strategy = select_deception_strategy(npc, context_risk)
    return strategy != "none"


def build_expressed_state(npc: Dict[str, Any], context_risk: float = 0.5) -> Dict[str, str]:
    """
    Build the NPC's *expressed* state which may differ from their true intent.

    Uses the deception strategy to determine *how* to distort (not just whether).
    """
    true_action = npc.get("current_action", "idle")
    true_emotion = max(
        npc.get("emotional_state", {"neutral": 0.5}).items(),
        key=lambda x: x[1],
        default=("neutral", 0.5),
    )

    strategy = select_deception_strategy(npc, context_risk)
    npc["deception_mode"] = strategy

    if strategy == "none" or strategy == "signal":
        # Honest or strategic reveal
        expressed_action = true_action
        expressed_emotion = true_emotion[0]
    elif strategy == "conceal":
        # Hide hostile actions, show neutral
        conceal_map = {"attack": "idle", "confront": "idle", "scheme": "idle", "flee": "idle"}
        expressed_action = conceal_map.get(true_action, true_action)
        expressed_emotion = "calm" if true_emotion[0] in ("anger", "fear") else true_emotion[0]
    elif strategy == "distort":
        # Twist: show plausible alternative
        distort_map = {
            "attack": "talk",
            "confront": "observe",
            "scheme": "idle",
            "flee": "guard",
        }
        expressed_action = distort_map.get(true_action, true_action)
        expressed_emotion = "calm" if true_emotion[0] in ("anger", "fear") else true_emotion[0]
    elif strategy == "fabricate":
        # Full fabrication: show the opposite
        fabricate_map = {
            "attack": "help",
            "confront": "talk",
            "scheme": "trade",
            "flee": "guard",
            "deceive": "help",
        }
        expressed_action = fabricate_map.get(true_action, "talk")
        expressed_emotion = "friendly" if true_emotion[0] in ("anger", "fear", "contempt") else "calm"
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


# ── Theory of Mind ────────────────────────────────────────────────────────

def update_theory_of_mind(npc: Dict[str, Any], other_npcs: List[Dict[str, Any]]) -> None:
    """
    Update this NPC's model of what *others* believe.

    Uses the NPC's intelligence trait to determine accuracy.  Low intelligence
    NPCs have noisier models.  This enables manipulation, deception layers,
    and mind games.
    """
    intelligence = npc.get("personality_traits", {}).get("intelligent", 0.5)
    tom = dict(npc.get("theory_of_mind", {}))

    for other in other_npcs:
        other_name = other.get("name", "")
        if other_name == npc.get("name", ""):
            continue

        other_beliefs = other.get("beliefs", {})
        other_expressed = other.get("expressed_state", {})

        model: Dict[str, float] = dict(tom.get(other_name, {}))

        # High intelligence → read true beliefs; low → read expressed state
        if intelligence > 0.6:
            for key, val in other_beliefs.items():
                # Noisy observation: accuracy scales with intelligence
                noise = (1.0 - intelligence) * (random.random() - 0.5) * 0.4
                model[key] = clamp(val + noise)
        else:
            # Low intelligence: infer from expressed state only
            expressed_intent = other_expressed.get("intent", "idle")
            if expressed_intent in ("attack", "confront"):
                model["is_hostile"] = clamp(model.get("is_hostile", 0.5) + 0.2)
            elif expressed_intent in ("help", "trade"):
                model["is_friendly"] = clamp(model.get("is_friendly", 0.5) + 0.2)

        tom[other_name] = model

    npc["theory_of_mind"] = tom


# ── Personality Evolution ─────────────────────────────────────────────────

# How much a single action nudges a trait
_EVOLUTION_DELTA = 0.02
# Traits that can evolve and the actions that affect them
_EVOLUTION_MAP = {
    "aggressive": {"attack": +1, "confront": +1, "help": -1, "trade": -1, "flee": -1},
    "honest": {"deceive": -1, "fabricate": -1, "talk": +0.5, "help": +0.5},
    "loyal": {"help": +1, "scheme": -1, "betray": -2},
    "brave": {"attack": +1, "confront": +1, "flee": -1, "guard": +0.5},
    "greedy": {"trade": +0.5, "steal": +1, "help": -0.5, "gift": -1},
}


def evolve_personality(npc: Dict[str, Any], action: str) -> None:
    """
    Nudge personality traits based on the action the NPC performed.

    Repeated aggressive actions make NPCs more aggressive over time.
    Repeated kind actions make them less aggressive.  Changes are small
    (±0.02 per action) to ensure gradual, believable evolution.
    """
    traits = npc.get("personality_traits", {})
    deception_mode = npc.get("deception_mode", "none")

    for trait, action_map in _EVOLUTION_MAP.items():
        if action in action_map:
            delta = action_map[action] * _EVOLUTION_DELTA
            traits[trait] = clamp(traits.get(trait, 0.5) + delta)

    # Deception also affects honesty
    if deception_mode in ("fabricate", "distort"):
        traits["honest"] = clamp(traits.get("honest", 0.5) - _EVOLUTION_DELTA)
    elif deception_mode == "signal":
        traits["honest"] = clamp(traits.get("honest", 0.5) + _EVOLUTION_DELTA * 0.5)

    npc["personality_traits"] = traits


# ── World Event Memory Integration ───────────────────────────────────────

def absorb_world_events(npc: Dict[str, Any], world_events: List[str]) -> None:
    """
    Feed global world events into an NPC's memory.

    NPCs become aware of world-level events (war, famine, etc.) which
    synchronises the world — NPCs don't exist in isolation.
    """
    memories = npc.get("memories", [])
    known_events = {m.get("action", "") for m in memories if m.get("actor") == "world"}

    for event_text in world_events[-5:]:  # Only recent events
        if event_text not in known_events:
            memories.append({
                "actor": "world",
                "action": event_text,
                "importance": 0.6,
                "emotion": "",
                "intensity": 0.0,
            })

    npc["memories"] = memories


# ── Faction Strategy ──────────────────────────────────────────────────────

_VALID_STRATEGIES = frozenset({"expand", "defend", "deceive", "trade", "neutral"})


def update_faction_strategy(faction: Dict[str, Any]) -> str:
    """
    Update a faction's strategy based on its current relations and power.

    Strategy is driven by faction health:
      - Many enemies → defend
      - Losing → deceive
      - Economically strong → trade
      - Dominant → expand
      - Otherwise → neutral
    """
    relations = faction.get("relations", {})
    enemy_count = sum(1 for v in relations.values() if v < -30)
    ally_count = sum(1 for v in relations.values() if v > 30)
    avg_relation = sum(relations.values()) / max(len(relations), 1)

    ideology = faction.get("ideology", {})
    commerce = ideology.get("commerce", 0.0)
    violence = ideology.get("violence", 0.0)
    ambition = ideology.get("ambition", 0.0)

    if enemy_count >= 2:
        strategy = "defend"
    elif avg_relation < -20:
        strategy = "deceive"
    elif commerce > 0.6 and ally_count >= 1:
        strategy = "trade"
    elif ambition > 0.6 or violence > 0.6:
        strategy = "expand"
    else:
        strategy = "neutral"

    faction["strategy"] = strategy
    return strategy


# ── LLM Prompt Builder ───────────────────────────────────────────────────

def build_npc_prompt(
    npc: Dict[str, Any],
    plan: List[str],
    player_input: str = "",
    world_context: str = "",
) -> Tuple[str, str]:
    """
    Build the system prompt and user prompt for an NPC's LLM decision call.

    Includes deception strategy, theory of mind, and emotional context.
    Returns (system_prompt, user_prompt).
    """
    name = npc.get("name", "Unknown NPC")
    role = npc.get("role", "villager")
    traits = npc.get("personality_traits", {})
    beliefs = npc.get("beliefs", {})
    memory_summary = npc.get("memory_summary", "No significant memories.")
    expressed = npc.get("expressed_state", {})
    deception_mode = npc.get("deception_mode", "none")
    tom = npc.get("theory_of_mind", {})

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
            f"Style: {style}\n"
        )

        # Deception strategy guidance
        if deception_mode != "none":
            system_prompt += (
                f"\nDeception Strategy:\n"
                f"- Mode: {deception_mode}\n"
                f"- Goal: avoid revealing true intent while appearing cooperative\n"
            )

        # Theory of mind: what NPC thinks player believes
        player_tom = tom.get("player", {})
        if player_tom:
            tom_str = ", ".join(f"{k}: {v:.2f}" for k, v in player_tom.items())
            system_prompt += f"\nYou believe the player thinks: {tom_str}\n"

        system_prompt += (
            "\nRules:\n"
            "- You may lie if your honesty trait is low and it benefits you\n"
            "- You do not reveal secrets easily\n"
            "- Your actions must be consistent with your personality\n"
            "- You may override the GOAP plan if you have a strategic reason\n\n"
            "Respond with ONLY valid JSON:\n"
            '{"action": "...", "dialogue": "...", "intent": "...", "emotion": "...", '
            '"override": false, "reason": ""}\n'
            "action must be one of: attack, flee, trade, help, scheme, guard, "
            "confront, talk, deceive, observe, idle\n"
            "Set override=true and provide reason if deviating from the plan."
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
    Supports LLM plan override: if ``override`` is True and ``reason`` is
    provided, the LLM's action is accepted as a strategic deviation.
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
        "override": bool(result.get("override", False)),
        "reason": str(result.get("reason", ""))[:200],
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
    world_events: Optional[List[str]] = None,
    other_npcs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Full NPC mind pipeline:

        Memory → Beliefs → Goals → GOAP Plan → LLM Interpretation → Action

    Now includes:
      - World event memory absorption
      - Causal belief updates
      - Emotional memory tagging
      - Theory of mind updates
      - Deception strategy selection
      - LLM plan override support
      - Personality evolution

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
    world_events : list of str, optional
        Recent global world events to absorb.
    other_npcs : list of dict, optional
        Other NPCs for theory of mind updates.

    Returns
    -------
    dict
        ``{"action", "dialogue", "intent", "emotion", "override", "reason"}``
    """
    # 1. Absorb global world events into NPC memory
    if world_events:
        absorb_world_events(npc, world_events)

    # 2. Decay old unimportant memories
    decay_memories(npc)

    # 3. Update beliefs from memories + emotions (causal graph)
    update_beliefs(npc)

    # 4. Summarise memory for LLM context (with emotional tags)
    summarize_memory(npc)

    # 5. Update theory of mind (model what others believe)
    if other_npcs:
        update_theory_of_mind(npc, other_npcs)

    # 6. Build expressed state (deception strategy layer)
    npc_location = npc.get("location", "")
    context_risk = 0.5
    beliefs = npc.get("beliefs", {})
    if beliefs.get("player_is_hostile", 0) > 0.6:
        context_risk = 0.8
    build_expressed_state(npc, context_risk)

    # 7. Select highest-priority goal
    goal = select_goal(npc)
    plan = [goal.get("type", "idle")] if goal else ["idle"]

    # 8. Determine intelligence tier
    tier = get_intelligence_tier(npc_location, player_location, location_distances)

    # 9. Tier 2+: GOAP-only (no LLM call)
    if tier >= TIER_GOAP or llm_call_fn is None:
        goap_result = goap_decide(npc, world_context)
        # Still evolve personality based on GOAP action
        evolve_personality(npc, goap_result["action"])
        return goap_result

    # 10. Tier 1: Full LLM reasoning
    system_prompt, user_prompt = build_npc_prompt(
        npc, plan, player_input, world_context,
    )

    raw_response = llm_call_fn(system_prompt, user_prompt)
    if not raw_response:
        goap_result = goap_decide(npc, world_context)
        evolve_personality(npc, goap_result["action"])
        return goap_result

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
        goap_result = goap_decide(npc, world_context)
        evolve_personality(npc, goap_result["action"])
        return goap_result

    # 11. Validate LLM output strictly (with override support)
    validated = validate_npc_action(parsed)

    # 12. LLM plan override: if LLM chose to deviate strategically
    if validated.get("override") and validated.get("reason"):
        logger.info("NPC %s: LLM override — %s (reason: %s)",
                     npc.get("name", "?"), validated["action"], validated["reason"])

    # 13. Evolve personality based on chosen action
    evolve_personality(npc, validated["action"])

    return validated
