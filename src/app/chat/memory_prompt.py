"""Resolve an active frozen memory snapshot into trusted prompt items."""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from app.assistant_memory import MemoryService, default_memory_service, resolve_chat_scope
from app.assistant_memory.lifecycle import resolve_snapshot_view

from .models import ChatSession
from .prompt_assembly import PromptMemoryItem


def chat_memory_enabled() -> bool:
    return (os.environ.get("OMNIX_CHAT_MEMORY_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_prompt_memory(
    session: ChatSession,
    *,
    memory_service_factory: Callable[[], MemoryService] = default_memory_service,
) -> tuple[list[PromptMemoryItem], dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "memory_enabled": bool(chat_memory_enabled() and session.memory_enabled),
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
    if not session.memory_enabled:
        diagnostics["status"] = "disabled_for_session"
        return [], diagnostics
    if not session.memory_snapshot_id:
        diagnostics["status"] = "snapshot_missing"
        return [], diagnostics

    service = memory_service_factory()
    context = resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )
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
        selected.append(
            PromptMemoryItem(
                memory_id=item.memory_record_id,
                content=item.content,
                scope=record.scope,
                category=record.category,
                revision=item.record_revision,
            )
        )

    diagnostics.update(
        {
            "status": "ready",
            "selected_memory_ids": [item.memory_id for item in selected],
            "selected_memory_count": len(selected),
            "invalidated_count": view.invalidated_count,
            "excluded_reason_counts": excluded,
            "memory_token_estimate": view.token_estimate,
        }
    )
    return selected, diagnostics
