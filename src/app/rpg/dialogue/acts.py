"""Phase 8.1 — Dialogue Acts Registry.

Central registry and deterministic mapping for dialogue acts.
Maps structured NPC agency outcomes, social state, and arc pressure
to supported dialogue acts.

All functions are pure, deterministic, and easy to unit test.
"""

from __future__ import annotations

from typing import Any


# ------------------------------------------------------------------
# Supported dialogue acts
# ------------------------------------------------------------------

SUPPORTED_DIALOGUE_ACTS = frozenset({
    "question",
    "refusal",
    "agreement",
    "threat",
    "redirect",
    "offer",
    "reveal_hint",
    "reassure",
    "warn",
    "probe",
    "stall",
    "acknowledge",
})


# ------------------------------------------------------------------
# NPC outcome → primary act
# ------------------------------------------------------------------

_OUTCOME_TO_ACT: dict[str, str] = {
    "agree": "agreement",
    "assist": "agreement",
    "refuse": "refusal",
    "threaten": "threat",
    "redirect": "redirect",
    "delay": "stall",
    "suspicious": "probe",
    "warn": "warn",
    "offer": "offer",
    "reveal": "reveal_hint",
    "reassure": "reassure",
}


def map_npc_outcome_to_primary_act(outcome: str) -> str:
    """Map an NPC agency outcome string to a supported dialogue act.

    Returns ``'acknowledge'`` for unknown outcomes.
    """
    return _OUTCOME_TO_ACT.get(outcome, "acknowledge")


# ------------------------------------------------------------------
# Relationship → tone
# ------------------------------------------------------------------

def map_relationship_to_tone(rel: dict[str, Any]) -> str:
    """Derive a tone label from a relationship state dict.

    Uses trust, hostility, fear, and respect to pick a deterministic
    tone.  Priority order:
        1. High hostility → ``'hostile'``
        2. High fear → ``'fearful'``
        3. High trust → ``'warm'``
        4. High respect → ``'formal'``
        5. Fallback → ``'neutral'``
    """
    trust = float(rel.get("trust", 0.0))
    hostility = float(rel.get("hostility", 0.0))
    fear = float(rel.get("fear", 0.0))
    respect = float(rel.get("respect", 0.0))

    if hostility >= 0.6:
        return "hostile"
    if fear >= 0.6:
        return "fearful"
    if trust >= 0.6:
        return "warm"
    if respect >= 0.6:
        return "formal"
    return "neutral"


# ------------------------------------------------------------------
# Relationship → stance
# ------------------------------------------------------------------

def map_relationship_to_stance(rel: dict[str, Any]) -> str:
    """Derive a stance label from a relationship state dict.

    Priority order:
        1. High hostility & high fear → ``'defensive'``
        2. High hostility → ``'aggressive'``
        3. High trust & low hostility → ``'cooperative'``
        4. High fear → ``'defensive'``
        5. Fallback → ``'neutral'``
    """
    trust = float(rel.get("trust", 0.0))
    hostility = float(rel.get("hostility", 0.0))
    fear = float(rel.get("fear", 0.0))

    if hostility >= 0.6 and fear >= 0.6:
        return "defensive"
    if hostility >= 0.6:
        return "aggressive"
    if trust >= 0.6 and hostility < 0.3:
        return "cooperative"
    if fear >= 0.6:
        return "defensive"
    return "neutral"


# ------------------------------------------------------------------
# Arc pressure → reveal level
# ------------------------------------------------------------------

def map_arc_pressure_to_reveal_level(arc_context: dict[str, Any]) -> str:
    """Derive a reveal level from arc context.

    Examines ``due_reveals`` and ``active_pacing_plan`` to determine
    whether the NPC should hint at or withhold information.

    Returns one of: ``'none'``, ``'low'``, ``'medium'``, ``'high'``.
    """
    due_reveals = arc_context.get("due_reveals", [])
    pacing = arc_context.get("active_pacing_plan") or {}
    bias = arc_context.get("active_scene_bias") or {}

    if due_reveals:
        return "high"

    scene_type = bias.get("scene_type_bias", "")
    if scene_type in ("revelatory", "climax"):
        return "high"
    if scene_type in ("tense", "urgent"):
        return "medium"

    tempo = pacing.get("tempo", "normal")
    if tempo == "fast":
        return "medium"
    if tempo == "slow":
        return "low"

    return "none"


# ------------------------------------------------------------------
# Scene bias → dialogue shaping tags
# ------------------------------------------------------------------

def map_scene_bias_to_dialogue_tags(bias: dict[str, Any]) -> list[str]:
    """Map a scene-bias dict to dialogue shaping tags.

    Returns a list of tags such as ``['tense', 'guarded']``.
    """
    tags: list[str] = []
    scene_type = bias.get("scene_type_bias", "")
    _BIAS_TAG_MAP: dict[str, str] = {
        "tense": "tense",
        "guarded": "guarded",
        "urgent": "urgent",
        "revelatory": "revelatory",
        "misdirecting": "misdirecting",
        "calm": "calm",
        "climax": "urgent",
    }
    tag = _BIAS_TAG_MAP.get(scene_type)
    if tag:
        tags.append(tag)
    if bias.get("force_option_framing"):
        tags.append("framed")
    return tags


# ------------------------------------------------------------------
# Normalize
# ------------------------------------------------------------------

def normalize_dialogue_act(value: str) -> str:
    """Normalize a dialogue act string to a supported act.

    Returns the act if supported, otherwise ``'acknowledge'``.
    """
    normalized = value.strip().lower()
    if normalized in SUPPORTED_DIALOGUE_ACTS:
        return normalized
    return "acknowledge"
