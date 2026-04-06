"""Phase 10 — RPG Presentation package.

Provides presentation builders for scene/dialogue payloads, speaker cards,
and personality style helpers used by both the API layer and frontend rendering.
"""
from .personality import (
    build_personality_prompt_hints,
    build_personality_style_tags,
)
from .personality_state import (
    ensure_personality_state,
    get_actor_personality_profile,
    build_personality_summary,
)
from .speaker_cards import (
    build_speaker_cards,
    build_party_speaker_cards,
)
from .scene_presentation import (
    build_scene_presentation_payload,
)
from .dialogue_presentation import (
    build_dialogue_presentation_payload,
)
from .dialogue_prompt_builder import (
    build_dialogue_llm_payload,
    build_scene_llm_payload,
)
from .dialogue_fallbacks import (
    build_deterministic_dialogue_fallback,
    build_deterministic_scene_fallback,
)
from .runtime_bridge import (
    build_runtime_presentation_payload,
)
from .orchestration_bridge import (
    build_orchestration_presentation_payload,
)
from .live_provider_bridge import (
    build_live_provider_presentation_payload,
)

__all__ = [
    "build_personality_prompt_hints",
    "build_personality_style_tags",
    "ensure_personality_state",
    "get_actor_personality_profile",
    "build_personality_summary",
    "build_speaker_cards",
    "build_party_speaker_cards",
    "build_scene_presentation_payload",
    "build_dialogue_presentation_payload",
    "build_dialogue_llm_payload",
    "build_scene_llm_payload",
    "build_deterministic_dialogue_fallback",
    "build_deterministic_scene_fallback",
    "build_runtime_presentation_payload",
    "build_orchestration_presentation_payload",
    "build_live_provider_presentation_payload",
]
