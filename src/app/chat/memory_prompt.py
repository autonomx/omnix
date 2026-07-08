"""Resolve an active frozen memory snapshot into trusted prompt items."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.assistant_memory import (
    MemoryService,
    default_memory_service,
    resolve_session_memory_scope,
    resolve_snapshot_view,
)
from app.assistant_memory.settings import load_memory_runtime_settings

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
    diagnostics: dict[str, Any] = {
        "memory_enabled": bool(chat_memory_enabled() and read_allowed),
        "owner_type": "character" if character_session else "system",
        "owner_id": session.character_id if character_session else "system-assistant",
        "snapshot_id": session.memory_snapshot_id,
        "snapshot_revision": session.memory_snapshot_revision,
        "selected_memory_ids": [],
        "selected_memory_count": 0,
        "invalidated_count": 0,
        "excluded_reason_counts": {},
    }
    if not chat_memory_enabled():
        diagnostics["status"] = "disabled_by_feature_flag"
        return [], diagnostics
    if not read_allowed:
        diagnostics["status"] = "disabled_for_session"
        return [], diagnostics
    if not session.memory_snapshot_id:
        diagnostics["status"] = "snapshot_missing"
        return [], diagnostics

    service = memory_service_factory()
    context = resolve_session_memory_scope(session)
    view = resolve_snapshot_view(service, context, session.memory_snapshot_id)
    if view is None:
        diagnostics["status"] = "snapshot_unavailable"
        return [], diagnostics

    selected: list[PromptMemoryItem] = []
    excluded: dict[str, int] = {}
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
            )
        )

    diagnostics.update({
        "status": "resolved",
        "selected_memory_ids": [item.memory_id for item in selected],
        "selected_memory_count": len(selected),
        "invalidated_count": view.invalidated_count,
        "excluded_reason_counts": excluded,
    })
    return selected, diagnostics
