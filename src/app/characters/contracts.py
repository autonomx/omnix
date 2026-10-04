"""Stable character services consumed by neighboring feature modules."""
from __future__ import annotations

from importlib import import_module

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


# Services apps import through this contract, loaded on first use (ADR-0016).
_LAZY_EXPORTS = {
    "CharacterLiveCallRuntime": "live_call",
    "resolve_live_call_runtime": "live_call",
    "LiveConversationProfileEnvelope": "live_conversation_profile",
    "LiveConversationProfileUpdate": "live_conversation_profile",
    "CharacterDataActionRequest": "management",
    "CharacterDataActionResponse": "management",
    "CharacterDataExport": "management",
    "CharacterManagementService": "management",
    "CharacterConflictError": "repository",
    "CharacterNotFoundError": "repository",
    "CharacterService": "service",
    "character_hermes_sync_enabled": "interaction",
}


def __getattr__(name: str):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"app.characters.{module}"), name)
