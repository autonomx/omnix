"""Stable memory services consumed by prompt and conversation features."""
from __future__ import annotations

from typing import Any

from importlib import import_module

from app.platform.assistant_memory.owner_defaults import default_memory_service
from app.platform.assistant_memory.selection import estimate_memory_tokens, select_memory_records
from app.platform.assistant_memory.service import MemoryPolicyError, MemoryService
from app.platform.assistant_memory.session import RefreshSessionMemoryRequest, refresh_session_memory

from app.platform.assistant_memory.companion_context import build_companion_context_packet
from app.platform.assistant_memory.lifecycle import resolve_snapshot_view
from app.platform.assistant_memory.initiative import (
    initiative_prompt_directive,
    plan_companion_initiative,
)
from app.platform.assistant_memory.observability import (
    record_companion_diagnostics,
    record_memory_usage,
)
from app.platform.assistant_memory.paralinguistic_state import (
    observe_paralinguistic_turn,
    paralinguistic_prompt_directive,
)
from app.platform.assistant_memory.persistence.settings_store import ASSISTANT_MEMORY_SETTINGS_KEY
from app.platform.assistant_memory.rollout import companion_rollout_policy
from app.platform.assistant_memory.scope import resolve_chat_scope, resolve_session_memory_scope
from app.platform.assistant_memory.settings import (
    AssistantMemoryRuntimeSettings,
    load_memory_runtime_settings,
    use_memory_runtime_settings,
)
from app.platform.assistant_memory.temporal_retrieval import retrieve_temporal_context

def read_owner_understanding(owner_type: str, owner_id: str, profile_id: str) -> list[Any]:
    """What an owner has understood about this person (``v2/understanding_view``), loaded only when asked for."""
    from .v2.understanding_view import read_owner_understanding as read

    return read(owner_type, owner_id, profile_id)


def forget_owner_understanding(owner_type: str, owner_id: str, profile_id: str, kind: str, key: str) -> int:
    from .v2.understanding_view import forget_owner_understanding as forget

    return forget(owner_type, owner_id, profile_id, kind, key)


def correct_owner_understanding(owner_type: str, owner_id: str, profile_id: str, kind: str, key: str, text: str) -> bool:
    from .v2.understanding_view import correct_owner_understanding as correct

    return correct(owner_type, owner_id, profile_id, kind, key, text)


__all__ = [
    "correct_owner_understanding",
    "forget_owner_understanding",
    "read_owner_understanding",
    "ASSISTANT_MEMORY_SETTINGS_KEY",
    "AssistantMemoryRuntimeSettings",
    "MemoryPolicyError",
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
    """The owner-aware memory repository of this runtime: PostgreSQL when it is the authority (public API)."""
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        from app.platform.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository

        return OwnerAwareInMemoryMemoryRepository()
    from app.platform.assistant_memory.persistence.owner_memory_store import production_owner_memory_repository

    return production_owner_memory_repository()


# Services apps import through this contract, loaded on first use (ADR-0016).
_LAZY_EXPORTS = {
    "CharacterHermesSyncStatus": "character_hermes_adapter",
    "export_character_memory_to_hermes": "character_hermes_adapter",
    "import_character_hermes_memory": "character_hermes_adapter",
    # Memory v2's observation API, for modules that record observations (PA-3.2).
    "MemorySpaceKey": "v2.contracts",
    "ObservationProvenance": "v2.contracts",
    "VisibilityScope": "v2.contracts",
    "ObservationAppendRequest": "v2.observation_store",
    "PostgresMemoryV2Runtime": "v2.runtime",
}


def __getattr__(name: str):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"app.platform.assistant_memory.{module}"), name)
