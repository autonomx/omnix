"""Living-world NPC ambient dialogue engine.

Builds, selects, and prepares ambient dialogue candidates.
All selection is deterministic — sorted ordering, stable salience, stable tie-breaking.
No uncontrolled randomness.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v) if not isinstance(v, str) else v


# ── Candidate types ───────────────────────────────────────────────────────

CANDIDATE_KINDS = (
    "npc_to_player",
    "npc_to_npc",
    "npc_reaction",
    "companion_comment",
    "warning",
    "demand",
    "taunt",
    "gossip",
)

# ── Cooldown constants ────────────────────────────────────────────────────

_DEFAULT_SPEAKER_COOLDOWN = 3   # ticks before same NPC can speak again
_DEFAULT_KIND_COOLDOWN = 2      # ticks before same kind fires again
_DEFAULT_PAIR_COOLDOWN = 5      # ticks before same speaker→target pair fires again


def _is_on_cooldown(cooldowns: Dict[str, Any], key: str, current_tick: int, cooldown_ticks: int) -> bool:
    """Check if a cooldown key is still active."""
    last_tick = int(cooldowns.get(key, -999) or -999)
    return (current_tick - last_tick) < cooldown_ticks


def _set_cooldown(cooldowns: Dict[str, Any], key: str, current_tick: int) -> None:
    """Record a cooldown activation."""
    cooldowns[key] = current_tick


# ── Build candidates ──────────────────────────────────────────────────────

def build_ambient_dialogue_candidates(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build a list of possible ambient dialogue candidates from simulation state.
    
    Considers NPC minds, decisions, relationships, and player context
    to generate candidates for NPC speech.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    player_context = _safe_dict(player_context)
    
    candidates: List[Dict[str, Any]] = []
    
    player_loc = _safe_str(player_context.get("player_location"))
    nearby_ids = set(_safe_list(player_context.get("nearby_npc_ids")))
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    npc_minds = _safe_dict(simulation_state.get("npc_minds"))
    npc_decisions = _safe_dict(simulation_state.get("npc_decisions"))
    tick = int(simulation_state.get("tick", 0) or 0)
    
    # Active encounter check: suppress chatter during active combat unless urgent
    encounter_active = bool(simulation_state.get("encounter_active") or simulation_state.get("active_encounter"))
    
    for npc_id in sorted(npc_index.keys()):
        npc_info = _safe_dict(npc_index.get(npc_id))
        npc_name = _safe_str(npc_info.get("name") or npc_id)
        npc_loc = _safe_str(npc_info.get("location_id"))
        
        # Only consider nearby NPCs or those at player location
        if npc_id not in nearby_ids and npc_loc != player_loc:
            continue
        
        mind = _safe_dict(npc_minds.get(npc_id))
        beliefs = _safe_dict(mind.get("beliefs"))
        goals = _safe_list(mind.get("goals"))
        decision = _safe_dict(npc_decisions.get(npc_id))
        
        player_belief = _safe_dict(beliefs.get("player"))
        trust = float(player_belief.get("trust", 0) or 0)
        hostility = float(player_belief.get("hostility", 0) or 0)
        
        # NPC → Player speech candidates
        if trust > 0.3:
            candidates.append({
                "kind": "npc_to_player",
                "speaker_id": npc_id,
                "speaker_name": npc_name,
                "target_id": "player",
                "target_name": "you",
                "salience": 0.5 + trust * 0.3,
                "text_hint": f"{npc_name} wants to speak with you.",
                "emotion": "friendly",
                "location_id": npc_loc,
                "tick": tick,
            })
        
        if hostility > 0.5 and not encounter_active:
            kind = "warning" if hostility < 0.8 else "taunt"
            candidates.append({
                "kind": kind,
                "speaker_id": npc_id,
                "speaker_name": npc_name,
                "target_id": "player",
                "target_name": "you",
                "salience": 0.6 + hostility * 0.3,
                "text_hint": f"{npc_name} eyes you {'warily' if kind == 'warning' else 'with menace'}.",
                "emotion": "hostile",
                "location_id": npc_loc,
                "tick": tick,
                "interrupt": hostility > 0.7,
            })
        
        # NPC → NPC speech candidates (between nearby NPCs)
        for other_id in sorted(npc_index.keys()):
            if other_id == npc_id:
                continue
            other_info = _safe_dict(npc_index.get(other_id))
            other_loc = _safe_str(other_info.get("location_id"))
            # Both must be at player's location
            if npc_loc != player_loc or other_loc != player_loc:
                continue
            
            other_belief = _safe_dict(beliefs.get(other_id))
            other_trust = float(other_belief.get("trust", 0) or 0)
            
            if other_trust > 0.2:
                other_name = _safe_str(other_info.get("name") or other_id)
                candidates.append({
                    "kind": "npc_to_npc",
                    "speaker_id": npc_id,
                    "speaker_name": npc_name,
                    "target_id": other_id,
                    "target_name": other_name,
                    "salience": 0.3 + other_trust * 0.2,
                    "text_hint": f"{npc_name} turns to speak with {other_name}.",
                    "emotion": "neutral",
                    "location_id": npc_loc,
                    "tick": tick,
                })
                break  # Only one NPC-to-NPC candidate per speaker
        
        # Companion commentary
        if _safe_str(npc_info.get("role")).lower() in ("companion", "ally", "follower"):
            candidates.append({
                "kind": "companion_comment",
                "speaker_id": npc_id,
                "speaker_name": npc_name,
                "target_id": "player",
                "target_name": "you",
                "salience": 0.4,
                "text_hint": f"{npc_name} has something to say.",
                "emotion": "thoughtful",
                "location_id": npc_loc,
                "tick": tick,
            })
        
        # Gossip (low priority, from NPCs with goals)
        if goals and not encounter_active:
            candidates.append({
                "kind": "gossip",
                "speaker_id": npc_id,
                "speaker_name": npc_name,
                "target_id": "",
                "target_name": "",
                "salience": 0.2,
                "text_hint": f"{npc_name} mutters something about their affairs.",
                "emotion": "neutral",
                "location_id": npc_loc,
                "tick": tick,
            })
    
    return candidates


# ── Cooldown-aware selection ──────────────────────────────────────────────

def select_ambient_dialogue_candidate(
    candidates: List[Dict[str, Any]],
    runtime_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Select the best ambient dialogue candidate respecting cooldowns.
    
    Selection is deterministic: sorted by salience descending, then by
    speaker_id for stable tie-breaking. Cooldowns suppress spam.
    """
    runtime_state = _safe_dict(runtime_state)
    cooldowns = _safe_dict(runtime_state.get("ambient_cooldowns"))
    current_tick = int(runtime_state.get("tick", 0) or 0)
    
    # Sort deterministically: highest salience first, then by speaker_id
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (-float(c.get("salience", 0) or 0), _safe_str(c.get("speaker_id"))),
    )
    
    for candidate in sorted_candidates:
        candidate = _safe_dict(candidate)
        speaker_id = _safe_str(candidate.get("speaker_id"))
        kind = _safe_str(candidate.get("kind"))
        target_id = _safe_str(candidate.get("target_id"))
        
        # Check cooldowns
        if _is_on_cooldown(cooldowns, f"speaker:{speaker_id}", current_tick, _DEFAULT_SPEAKER_COOLDOWN):
            continue
        if _is_on_cooldown(cooldowns, f"kind:{kind}", current_tick, _DEFAULT_KIND_COOLDOWN):
            continue
        if target_id and _is_on_cooldown(cooldowns, f"pair:{speaker_id}:{target_id}", current_tick, _DEFAULT_PAIR_COOLDOWN):
            continue
        
        # This candidate passes all cooldowns — select it
        return candidate
    
    return None


def apply_dialogue_cooldowns(runtime_state: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Apply cooldowns after a dialogue candidate is selected."""
    runtime_state = _safe_dict(runtime_state)
    cooldowns = dict(_safe_dict(runtime_state.get("ambient_cooldowns")))
    current_tick = int(runtime_state.get("tick", 0) or 0)
    
    speaker_id = _safe_str(candidate.get("speaker_id"))
    kind = _safe_str(candidate.get("kind"))
    target_id = _safe_str(candidate.get("target_id"))
    
    _set_cooldown(cooldowns, f"speaker:{speaker_id}", current_tick)
    _set_cooldown(cooldowns, f"kind:{kind}", current_tick)
    if target_id:
        _set_cooldown(cooldowns, f"pair:{speaker_id}:{target_id}", current_tick)
    
    runtime_state["ambient_cooldowns"] = cooldowns
    return runtime_state


def build_ambient_dialogue_request(candidate: Dict[str, Any], session_context: Dict[str, Any]) -> Dict[str, Any]:
    """Build an ambient dialogue request payload from a selected candidate.
    
    This creates the data structure used to either generate LLM dialogue
    or produce templated fallback text.
    """
    candidate = _safe_dict(candidate)
    session_context = _safe_dict(session_context)
    
    return {
        "kind": _safe_str(candidate.get("kind")),
        "speaker_id": _safe_str(candidate.get("speaker_id")),
        "speaker_name": _safe_str(candidate.get("speaker_name")),
        "target_id": _safe_str(candidate.get("target_id")),
        "target_name": _safe_str(candidate.get("target_name")),
        "text_hint": _safe_str(candidate.get("text_hint")),
        "emotion": _safe_str(candidate.get("emotion")),
        "location_id": _safe_str(candidate.get("location_id")),
        "tick": int(candidate.get("tick", 0) or 0),
        "scene_id": _safe_str(session_context.get("scene_id")),
        "world_context": _safe_str(session_context.get("world_summary")),
        "interrupt": bool(candidate.get("interrupt")),
    }
