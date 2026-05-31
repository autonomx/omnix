"""Split helpers for RPG world scene narration."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405
from app.rpg.ai.world_scene_narrator_common import *

_AMBIENT_TEMPLATES = {
    "npc_to_player": "{speaker_name} turns to you: \"{text}\"",
    "npc_to_npc": "{speaker_name} speaks to {target_name}: \"{text}\"",
    "npc_reaction": "{speaker_name} reacts: \"{text}\"",
    "companion_comment": "{speaker_name} says: \"{text}\"",
    "warning": "{speaker_name} warns: \"{text}\"",
    "demand": "{speaker_name} demands: \"{text}\"",
    "taunt": "{speaker_name} taunts: \"{text}\"",
    "gossip": "{speaker_name} mutters: \"{text}\"",
    "world_event": "{text}",
    "arrival": "{text}",
    "departure": "{text}",
    "combat_start": "⚔️ {text}",
    "system_summary": "📜 {text}",
}

_AMBIENT_PROMPTS = {
    "npc_to_player": (
        "You are {speaker_name}, an NPC in a living fantasy world. "
        "Write one short sentence addressed to the player. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "npc_to_npc": (
        "You are {speaker_name}, an NPC. Write one short sentence spoken to {target_name}. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "companion_comment": (
        "You are {speaker_name}, a companion of the player. "
        "Write one short observation or comment about the current situation. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "warning": (
        "You are {speaker_name}. Write a brief, tense warning directed at the player. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "world_event": (
        "Write one concise sentence narrating this world event for the player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the narration sentence."
    ),
    "system_summary": (
        "Summarize these world changes in one or two sentences for a returning player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the summary."
    ),
}


def narrate_ambient_update(
    *,
    ambient_update: Dict[str, Any],
    simulation_state: Dict[str, Any],
    current_scene: Dict[str, Any],
    llm_gateway: Any = None,
) -> Dict[str, Any]:
    """Narrate an ambient update for player presentation.

    If LLM is available, uses it for stylistic phrasing.
    Always falls back to deterministic templates if LLM is unavailable.
    LLM only styles phrasing — never invents world truth.

    Returns:
        {
            "text": str,
            "speaker_turns": list,
            "used_app_llm": bool,
            "raw_llm_narrative": str,
            "structured": dict,
        }
    """
    ambient_update = _safe_dict(ambient_update)
    simulation_state = _safe_dict(simulation_state)
    current_scene = _safe_dict(current_scene)

    kind = _safe_str(ambient_update.get("kind"))
    speaker_id = _safe_str(ambient_update.get("speaker_id"))
    speaker_name = _safe_str(ambient_update.get("speaker_name")) or speaker_id
    target_name = _safe_str(ambient_update.get("target_name"))
    raw_text = _safe_str(ambient_update.get("text"))
    emotion = _safe_str(ambient_update.get("emotion")) or "neutral"

    # Build scene context summary for LLM prompt
    scene_summary = _safe_str(current_scene.get("summary") or current_scene.get("scene"))
    context = scene_summary[:200] if scene_summary else "The world stirs."

    used_llm = False
    raw_llm_narrative = ""
    narrated_text = raw_text

    # Try LLM narration if available
    if llm_gateway and kind in _AMBIENT_PROMPTS:
        try:
            prompt_template = _AMBIENT_PROMPTS[kind]
            prompt = prompt_template.format(
                speaker_name=speaker_name,
                target_name=target_name,
                emotion=emotion,
                context=context,
                text=raw_text,
            )
            llm_response = _llm_text(llm_gateway, prompt)
            if llm_response and "[ERROR:" not in llm_response:
                narrated_text = _bound_text(llm_response.strip(), 250)
                raw_llm_narrative = llm_response
                used_llm = True
        except Exception:
            pass  # Fall through to template

    # Template fallback
    if not used_llm:
        template = _AMBIENT_TEMPLATES.get(kind, "{text}")
        narrated_text = template.format(
            speaker_name=speaker_name,
            target_name=target_name,
            text=raw_text,
        )

    # Build speaker turns for dialogue rendering
    speaker_turns: List[Dict[str, Any]] = []
    if speaker_id and kind in ("npc_to_player", "npc_to_npc", "companion_comment", "warning", "demand", "taunt", "gossip", "npc_reaction"):
        speaker_turns.append({
            "speaker_id": speaker_id,
            "name": speaker_name,
            "text": narrated_text,
            "emotion": emotion,
            "ambient": True,
        })

    return {
        "text": narrated_text,
        "speaker_turns": speaker_turns,
        "used_app_llm": used_llm,
        "raw_llm_narrative": raw_llm_narrative,
        "structured": {
            "kind": kind,
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "target_id": _safe_str(ambient_update.get("target_id")),
            "target_name": target_name,
            "ambient": True,
        },
    }

__all__ = [name for name in globals() if not name.startswith("__")]
