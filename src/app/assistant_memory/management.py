"""Typed management contracts and scope-bound memory operations."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat import ChatSession, ChatSessionStore

from .models import MemoryCandidate, MemoryCategory, MemoryRecord, MemoryScope
from .scope import resolve_chat_scope, scope_id_for
from .service import MemoryService


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MemoryRecord]
    total: int = Field(ge=0)
    session_id: str


class MemoryCandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[MemoryCandidate]
    total: int = Field(ge=0)
    session_id: str


class CreateManagedMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    scope: MemoryScope
    category: MemoryCategory
    content: str = Field(min_length=1, max_length=4096)
    pinned: bool = False


class UpdateManagedMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=4096)


class RevisionedMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)


class MoveManagedMemoryRequest(RevisionedMemoryRequest):
    target_scope: MemoryScope


class CandidateResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    pinned: bool = False


class ForgetMemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True
    memory_id: str


def resolve_session_scope(store: ChatSessionStore, session_id: str):
    session = store.get_session(session_id)
    if session is None:
        return None, None
    return session, resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )


def records_for_session(
    store: ChatSessionStore,
    service: MemoryService,
    session_id: str,
    *,
    scope: MemoryScope | None = None,
    category: MemoryCategory | None = None,
    pinned_only: bool = False,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> MemoryListResponse | None:
    _, context = resolve_session_scope(store, session_id)
    if context is None:
        return None
    normalized_query = " ".join((query or "").strip().split()).casefold()
    records = service.list_active(context)
    filtered = [
        record
        for record in records
        if (scope is None or record.scope == scope)
        and (category is None or record.category == category)
        and (not pinned_only or record.pinned)
        and (
            not normalized_query
            or normalized_query in record.normalized_content
            or normalized_query in record.content.casefold()
        )
    ]
    filtered.sort(key=lambda record: (not record.pinned, record.scope, record.category, record.id))
    total = len(filtered)
    bounded_limit = max(0, min(limit, 500))
    bounded_offset = max(0, offset)
    return MemoryListResponse(
        records=filtered[bounded_offset : bounded_offset + bounded_limit],
        total=total,
        session_id=session_id,
    )


def candidates_for_session(
    store: ChatSessionStore,
    service: MemoryService,
    session_id: str,
    *,
    limit: int = 100,
) -> MemoryCandidateListResponse | None:
    _, context = resolve_session_scope(store, session_id)
    if context is None:
        return None
    allowed_scope_ids = {
        scope_id
        for scope in ("global", "workspace", "project", "session")
        if (scope_id := scope_id_for(scope, context)) is not None
    }
    candidates = [
        candidate
        for candidate in service.repository.list_candidates(status="pending", limit=500)
        if candidate.proposed_scope_id in allowed_scope_ids
    ]
    candidates.sort(key=lambda candidate: (candidate.created_at, candidate.id))
    bounded_limit = max(0, min(limit, 500))
    return MemoryCandidateListResponse(
        candidates=candidates[:bounded_limit],
        total=len(candidates),
        session_id=session_id,
    )
