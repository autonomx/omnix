"""Stable memory services consumed by prompt and conversation features."""
from __future__ import annotations

from importlib import import_module

from app.assistant_memory.owner_defaults import default_memory_service
from app.assistant_memory.selection import estimate_memory_tokens, select_memory_records
from app.assistant_memory.service import MemoryService
from app.assistant_memory.session import RefreshSessionMemoryRequest, refresh_session_memory

from app.assistant_memory.companion_context import build_companion_context_packet
from app.assistant_memory.lifecycle import resolve_snapshot_view
from app.assistant_memory.initiative import (
    initiative_prompt_directive,
    plan_companion_initiative,
)
from app.assistant_memory.observability import (
    record_companion_diagnostics,
    record_memory_usage,
)
from app.assistant_memory.paralinguistic_state import (
    observe_paralinguistic_turn,
    paralinguistic_prompt_directive,
)
from app.assistant_memory.persistence.settings_store import ASSISTANT_MEMORY_SETTINGS_KEY
from app.assistant_memory.rollout import companion_rollout_policy
from app.assistant_memory.scope import resolve_chat_scope, resolve_session_memory_scope
from app.assistant_memory.settings import (
    AssistantMemoryRuntimeSettings,
    load_memory_runtime_settings,
    use_memory_runtime_settings,
)
from app.assistant_memory.temporal_retrieval import retrieve_temporal_context

__all__ = [
    "ASSISTANT_MEMORY_SETTINGS_KEY",
    "AssistantMemoryRuntimeSettings",
    "MemoryService",
    "RefreshSessionMemoryRequest",
    "build_companion_context_packet",
    "companion_rollout_policy",
    "default_memory_service",
    "estimate_memory_tokens",
    "initiative_prompt_directive",
    "load_memory_runtime_settings",
    "observe_paralinguistic_turn",
    "paralinguistic_prompt_directive",
    "plan_companion_initiative",
    "record_companion_diagnostics",
    "record_memory_usage",
    "refresh_session_memory",
    "resolve_session_memory_scope",
    "resolve_chat_scope",
    "resolve_snapshot_view",
    "retrieve_temporal_context",
    "select_memory_records",
    "use_memory_runtime_settings",
]


def owner_memory_repository():
    """The owner-aware memory repository for the PostgreSQL runtime (public API)."""
    from app.assistant_memory.persistence.owner_memory_store import production_owner_memory_repository

    return production_owner_memory_repository()


# Services apps import through this contract, loaded on first use (ADR-0016).
_LAZY_EXPORTS = {
    "CharacterHermesSyncStatus": "character_hermes_adapter",
    "export_character_memory_to_hermes": "character_hermes_adapter",
    "import_character_hermes_memory": "character_hermes_adapter",
}


def __getattr__(name: str):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"app.assistant_memory.{module}"), name)
