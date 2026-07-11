"""Compatibility facade for the canonical RPG response-generation pipeline.

Provider generation remains in the legacy split modules during migration, but final
visible narration is owned by ``RpgResponseGenerator`` through the explicit bridge.
This module intentionally contains no star imports, import-order fixups, or runtime
monkey patches.
"""
from __future__ import annotations

from app.rpg.ai.world_scene_narrator_prompts import (
    NPCReaction,
    NarrativeResult,
    build_choice_prompt,
    build_npc_reaction_prompt,
    build_scene_prompt,
    parse_choices,
    parse_npc_reaction,
    parse_scene_response,
)
from app.rpg.response_generation.legacy_bridge import (
    SceneNarrator,
    apply_legacy_narration_emphasis,
    narrate_scene_canonical,
    play_scene,
)

narrate_scene = narrate_scene_canonical

__all__ = [
    "NPCReaction",
    "NarrativeResult",
    "SceneNarrator",
    "apply_legacy_narration_emphasis",
    "build_choice_prompt",
    "build_npc_reaction_prompt",
    "build_scene_prompt",
    "narrate_scene",
    "parse_choices",
    "parse_npc_reaction",
    "parse_scene_response",
    "play_scene",
]
