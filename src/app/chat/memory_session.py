"""Atomic session metadata updates for frozen Chat memory snapshots."""
from __future__ import annotations

from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.assistant_memory import MemoryService, resolve_chat_scope
from app.assistant_memory.lifecycle import MemorySnapshotView, resolve_snapshot_view

from .concurrency import CHAT_MUTATION_LOCK
from .models import ChatSession

_SESSION_MEMORY_LOCK = RLock()


class SessionStoreLike(Protocol):
    def get_session(self, session_id: str) -> ChatSession | None: ...

    def _load_sessions(self) -> list[ChatSession]: ...

    def _save_sessions(self, sessions: list[ChatSession]) -> None: ...


class RefreshSessionMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_snapshot_revision: int | None = Field(default=None, ge=1)
    token_budget: int = Field(default=4_000, ge=0, le=64_000)


class SessionMemoryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    memory_enabled: bool
    snapshot_id: str | None = None
    snapshot_revision: int | None = Field(default=None, ge=1)
    memory_record_count: int = Field(default=0, ge=0)
    last_refreshed_at: str | None = None
    snapshot: MemorySnapshotView | None = None


class SessionMemoryConflictError(RuntimeError):
    pass


def _scope_for(session: ChatSession):
    return resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )


def get_session_memory_state(
    store: SessionStoreLike,
    memory_service: MemoryService,
    session_id: str,
) -> SessionMemoryState | None:
    session = store.get_session(session_id)
    if session is None:
        return None
    view = None
    if session.memory_snapshot_id:
        view = resolve_snapshot_view(
            memory_service,
            _scope_for(session),
            session.memory_snapshot_id,
        )
    active_count = view.active_count if view is not None else 0
    return SessionMemoryState(
        session_id=session.id,
        memory_enabled=session.memory_enabled,
        snapshot_id=session.memory_snapshot_id,
        snapshot_revision=session.memory_snapshot_revision,
        memory_record_count=active_count,
        last_refreshed_at=session.memory_last_refreshed_at,
        snapshot=view,
    )


def refresh_session_memory(
    store: SessionStoreLike,
    memory_service: MemoryService,
    session_id: str,
    request: RefreshSessionMemoryRequest,
) -> SessionMemoryState | None:
    with _SESSION_MEMORY_LOCK, CHAT_MUTATION_LOCK:
        sessions = store._load_sessions()
        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue
            current_revision = session.memory_snapshot_revision
            if (
                request.expected_snapshot_revision is not None
                and request.expected_snapshot_revision != current_revision
            ):
                raise SessionMemoryConflictError(
                    "memory snapshot revision conflict: "
                    f"expected {request.expected_snapshot_revision}, actual {current_revision}"
                )
            snapshot = memory_service.create_session_snapshot(
                _scope_for(session),
                token_budget=request.token_budget,
                refresh=current_revision is not None,
            )
            refreshed_at = snapshot.refreshed_at or snapshot.created_at
            session.memory_enabled = True
            session.memory_snapshot_id = snapshot.id
            session.memory_snapshot_revision = snapshot.revision
            session.memory_record_count = len(snapshot.items)
            session.memory_last_refreshed_at = refreshed_at
            session.updated_at = refreshed_at
            sessions[index] = session
            store._save_sessions(sessions)
            view = resolve_snapshot_view(memory_service, _scope_for(session), snapshot.id)
            return SessionMemoryState(
                session_id=session.id,
                memory_enabled=True,
                snapshot_id=snapshot.id,
                snapshot_revision=snapshot.revision,
                memory_record_count=view.active_count if view else 0,
                last_refreshed_at=refreshed_at,
                snapshot=view,
            )
    return None
