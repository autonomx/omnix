"""Resolve an active frozen memory snapshot into trusted prompt items."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.assistant_memory import (
    MemoryService,
    default_memory_service,
    resolve_chat_scope,
    resolve_session_memory_scope,
    resolve_snapshot_view,
    select_memory_records,
)
from app.assistant_memory.settings import load_memory_runtime_settings
from app.assistant_memory.selection import estimate_memory_tokens
from app.characters import resolve_shared_memory_categories

from .context_budget import prompt_budget_from_env
from .models import ChatSession
from .prompt_assembly import PromptMemoryItem


def chat_memory_enabled() -> bool:
    return load_memory_runtime_settings().curated_memory_enabled


def resolve_prompt_memory(
    session: ChatSession,
    *,
    memory_service_factory: Callable[[], MemoryService] = default_memory_service,
) -> tuple[list[PromptMemoryItem], dict[str, Any]]:
    character_session = session.interaction_mode == "character"
    read_allowed = session.read_memory if character_session else session.memory_enabled
    shared_categories = resolve_shared_memory_categories(session)
    shared_allowed = bool(shared_categories)
    diagnostics: dict[str, Any] = {
        "memory_enabled": bool(chat_memory_enabled() and (read_allowed or shared_allowed)),
        "owner_type": "character" if character_session else "system",
        "owner_id": session.character_id if character_session else "system-assistant",
        "snapshot_id": session.memory_snapshot_id,
        "snapshot_revision": session.memory_snapshot_revision,
        "selected_memory_ids": [],
        "selected_memory_count": 0,
        "invalidated_count": 0,
        "excluded_reason_counts": {},
        "shared_memory_access": session.shared_memory_access if character_session else "none",
        "shared_allowed_categories": shared_categories,
        "shared_selected_memory_ids": [],
        "shared_selected_memory_count": 0,
        "shared_excluded_reason_counts": {},
    }
    if not chat_memory_enabled():
        diagnostics["status"] = "disabled_by_feature_flag"
        return [], diagnostics
    if not read_allowed and not shared_allowed:
        diagnostics["status"] = "disabled_for_session"
        return [], diagnostics
    if read_allowed and not session.memory_snapshot_id:
        diagnostics["status"] = "snapshot_missing"
        return [], diagnostics

    service = memory_service_factory()
    selected: list[PromptMemoryItem] = []
    excluded: dict[str, int] = {}
    invalidated_count = 0
    if read_allowed:
        context = resolve_session_memory_scope(session)
        view = resolve_snapshot_view(service, context, session.memory_snapshot_id)
        if view is None:
            diagnostics["status"] = "snapshot_unavailable"
            return [], diagnostics
        invalidated_count = view.invalidated_count
        for item in view.items:
            if not item.active:
                reason = item.invalidation_reason or "invalidated"
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            record = service.repository.get_record(item.memory_record_id)
            if record is None:
                excluded["record_forgotten"] = excluded.get("record_forgotten", 0) + 1
                continue
            if (record.owner_type, record.owner_id) != (context.owner_type, context.owner_id):
                excluded["owner_mismatch"] = excluded.get("owner_mismatch", 0) + 1
                continue
            selected.append(
                PromptMemoryItem(
                    memory_id=item.memory_record_id,
                    content=item.content,
                    scope=record.scope,
                    category=record.category,
                    revision=item.record_revision,
                    source="character" if character_session else "system",
                )
            )

    shared_excluded: dict[str, int] = {}
    shared_selected: list[PromptMemoryItem] = []
    if shared_allowed:
        system_context = resolve_chat_scope(
            session.id,
            profile_id=session.profile_id,
            workspace_id=session.workspace_id,
            project_id=session.project_id,
        )
        candidates = []
        for record in service.list_active(system_context):
            reason = None
            if record.scope == "session":
                reason = "session_scope_blocked"
            elif record.category not in shared_categories:
                reason = "category_not_allowed"
            elif record.sensitivity != "normal":
                reason = "sensitivity_not_normal"
            if reason:
                shared_excluded[reason] = shared_excluded.get(reason, 0) + 1
            else:
                candidates.append(record)
        owner_tokens = sum(estimate_memory_tokens(item.content) for item in selected)
        token_budget = max(0, prompt_budget_from_env().memory_tokens - owner_tokens)
        shared_selection = select_memory_records(
            candidates,
            system_context,
            token_budget=token_budget,
        )
        for reason, count in shared_selection.diagnostics.excluded_reason_counts.items():
            shared_excluded[reason] = shared_excluded.get(reason, 0) + count
        shared_selected = [
            PromptMemoryItem(
                memory_id=record.id,
                content=record.content,
                scope=record.scope,
                category=record.category,
                revision=record.revision,
                source="shared_system",
            )
            for record in shared_selection.records
        ]
        selected.extend(shared_selected)

    diagnostics.update({
        "status": "resolved",
        "selected_memory_ids": [item.memory_id for item in selected],
        "selected_memory_count": len(selected),
        "invalidated_count": invalidated_count,
        "excluded_reason_counts": excluded,
        "shared_selected_memory_ids": [item.memory_id for item in shared_selected],
        "shared_selected_memory_count": len(shared_selected),
        "shared_excluded_reason_counts": shared_excluded,
    })
    return selected, diagnostics
