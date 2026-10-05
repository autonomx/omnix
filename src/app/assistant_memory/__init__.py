"""Backend-owned curated memory contracts, persistence, and policy.

Exports load on first use, so importing one submodule (``declarations``) does not
load the package (ADR-0016, PA-2.2).
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "DEFAULT_PROFILE_ID": ("app.assistant_memory.scope", "DEFAULT_PROFILE_ID"),
    "DEFAULT_WORKSPACE_ID": ("app.assistant_memory.scope", "DEFAULT_WORKSPACE_ID"),
    "InMemoryMemoryRepository": ("app.assistant_memory.repository", "InMemoryMemoryRepository"),
    "MemoryCandidate": ("app.memory_contracts", "MemoryCandidate"),
    "MemoryCategory": ("app.memory_contracts", "MemoryCategory"),
    "MemoryConflictError": ("app.assistant_memory.repository", "MemoryConflictError"),
    "MemoryNotFoundError": ("app.assistant_memory.repository", "MemoryNotFoundError"),
    "MemoryOwnerType": ("app.memory_contracts", "MemoryOwnerType"),
    "MemoryPolicyDecision": ("app.memory_contracts", "MemoryPolicyDecision"),
    "MemoryPolicyError": ("app.assistant_memory.service", "MemoryPolicyError"),
    "MemoryRecord": ("app.memory_contracts", "MemoryRecord"),
    "MemoryScope": ("app.memory_contracts", "MemoryScope"),
    "MemoryScopeContext": ("app.memory_contracts", "MemoryScopeContext"),
    "MemorySelection": ("app.assistant_memory.selection", "MemorySelection"),
    "MemorySelectionDiagnostics": ("app.assistant_memory.selection", "MemorySelectionDiagnostics"),
    "MemoryService": ("app.assistant_memory.service", "MemoryService"),
    "MemorySnapshot": ("app.memory_contracts", "MemorySnapshot"),
    "MemorySnapshotItem": ("app.memory_contracts", "MemorySnapshotItem"),
    "MemorySnapshotView": ("app.assistant_memory.lifecycle", "MemorySnapshotView"),
    "MemorySnapshotViewItem": ("app.assistant_memory.lifecycle", "MemorySnapshotViewItem"),
    "OwnerAwareInMemoryMemoryRepository": ("app.assistant_memory.owner_repository", "OwnerAwareInMemoryMemoryRepository"),
    "OwnerAwareMemoryService": ("app.assistant_memory.owner_service", "OwnerAwareMemoryService"),
    "RefreshSessionMemoryRequest": ("app.assistant_memory.session", "RefreshSessionMemoryRequest"),
    "SYSTEM_MEMORY_OWNER_ID": ("app.memory_contracts", "SYSTEM_MEMORY_OWNER_ID"),
    "SessionMemoryConflictError": ("app.assistant_memory.session", "SessionMemoryConflictError"),
    "SessionMemoryState": ("app.assistant_memory.session", "SessionMemoryState"),
    "candidate_acceptance": ("app.assistant_memory.policy", "candidate_acceptance"),
    "default_memory_db_path": ("app.assistant_memory.repository", "default_memory_db_path"),
    "default_memory_service": ("app.assistant_memory.owner_defaults", "default_memory_service"),
    "explicit_save_decision": ("app.assistant_memory.policy", "explicit_save_decision"),
    "get_session_memory_state": ("app.assistant_memory.session", "get_session_memory_state"),
    "is_expired": ("app.assistant_memory.policy", "is_expired"),
    "is_visible_in_scope": ("app.assistant_memory.policy", "is_visible_in_scope"),
    "move_scope_decision": ("app.assistant_memory.policy", "move_scope_decision"),
    "normalize_memory_content": ("app.assistant_memory.service", "normalize_memory_content"),
    "prompt_eligibility": ("app.assistant_memory.policy", "prompt_eligibility"),
    "refresh_session_memory": ("app.assistant_memory.session", "refresh_session_memory"),
    "resolve_chat_scope": ("app.assistant_memory.scope", "resolve_chat_scope"),
    "resolve_session_memory_scope": ("app.assistant_memory.scope", "resolve_session_memory_scope"),
    "resolve_snapshot_view": ("app.assistant_memory.lifecycle", "resolve_snapshot_view"),
    "scope_id_for": ("app.assistant_memory.scope", "scope_id_for"),
    "select_memory_records": ("app.assistant_memory.selection", "select_memory_records"),
    "source_requires_approval": ("app.assistant_memory.policy", "source_requires_approval"),
}

__all__ = [
    "DEFAULT_PROFILE_ID",
    "DEFAULT_WORKSPACE_ID",
    "InMemoryMemoryRepository",
    "MemoryCandidate",
    "MemoryCategory",
    "MemoryConflictError",
    "MemoryNotFoundError",
    "MemoryOwnerType",
    "MemoryPolicyDecision",
    "MemoryPolicyError",
    "MemoryRecord",
    "MemoryScope",
    "MemoryScopeContext",
    "MemorySelection",
    "MemorySelectionDiagnostics",
    "MemoryService",
    "MemorySnapshot",
    "MemorySnapshotItem",
    "MemorySnapshotView",
    "MemorySnapshotViewItem",
    "OwnerAwareInMemoryMemoryRepository",
    "OwnerAwareMemoryService",
    "SYSTEM_MEMORY_OWNER_ID",
    "RefreshSessionMemoryRequest",
    "SessionMemoryConflictError",
    "SessionMemoryState",
    "candidate_acceptance",
    "default_memory_db_path",
    "default_memory_service",
    "explicit_save_decision",
    "get_session_memory_state",
    "is_expired",
    "is_visible_in_scope",
    "move_scope_decision",
    "normalize_memory_content",
    "prompt_eligibility",
    "resolve_chat_scope",
    "resolve_session_memory_scope",
    "resolve_snapshot_view",
    "refresh_session_memory",
    "scope_id_for",
    "select_memory_records",
    "source_requires_approval",
]


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(target[0]), target[1])
    globals()[name] = value
    return value
