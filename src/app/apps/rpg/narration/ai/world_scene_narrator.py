"""Compatibility facade for the canonical RPG response-generation pipeline.

Provider generation remains in the legacy split modules during migration, but final
visible scene narration is owned by ``RpgResponseGenerator`` through the explicit
bridge. Ambient updates retain their deterministic dedicated presenter. This module
contains no star imports, import-order fixups, or runtime symbol replacement.
"""
from __future__ import annotations

from app.apps.rpg.narration.ai.world_scene_narrator_prompts import (
    build_choice_prompt,
    build_npc_reaction_prompt,
    build_scene_prompt,
    parse_choices,
    parse_npc_reaction,
    parse_scene_response,
)
from app.apps.rpg.narration.response_generation.legacy_bridge import (
    SceneNarrator,
    narrate_scene_canonical,
    play_scene,
)

narrate_scene = narrate_scene_canonical

__all__ = [
    "SceneNarrator",
    "build_choice_prompt",
    "build_npc_reaction_prompt",
    "build_scene_prompt",
    "narrate_scene",
    "parse_choices",
    "parse_npc_reaction",
    "parse_scene_response",
    "play_scene",
]
