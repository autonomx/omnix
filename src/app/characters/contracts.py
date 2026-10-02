"""Stable character services consumed by neighboring feature modules."""
from __future__ import annotations

from app.characters.interaction import (
    InteractionSelection,
    character_mode_enabled,
    neutralize_legacy_system_prompt,
    resolve_interaction_context,
    resolve_shared_memory_categories,
    resolve_system_session_identity,
)
from app.characters.live_conversation_profile import (
    LiveConversationProfile,
    LiveConversationProfileStore,
    default_live_conversation_profile_store,
)
from app.characters.service import (
    default_character_service,
    subscribe_character_snapshot_cache,
)
from app.characters.session_models import SetSessionInteractionRequest

__all__ = [
    "InteractionSelection",
    "LiveConversationProfile",
    "LiveConversationProfileStore",
    "SetSessionInteractionRequest",
    "character_mode_enabled",
    "default_character_service",
    "default_live_conversation_profile_store",
    "neutralize_legacy_system_prompt",
    "resolve_interaction_context",
    "resolve_shared_memory_categories",
    "resolve_system_session_identity",
    "subscribe_character_snapshot_cache",
]
