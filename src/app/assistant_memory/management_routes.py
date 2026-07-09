"""Internal browser-facing memory management routes."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

from app.chat import ChatSessionStore, default_chat_store

from .management import (
    CandidateCleanupRequest,
    CandidateResolutionRequest,
    CreateManagedMemoryRequest,
    ForgetCandidateResponse,
    ForgetMemoryResponse,
    MemoryCandidateListResponse,
    MemoryListResponse,
    MoveManagedMemoryRequest,
    RevisionedMemoryRequest,
    UpdateManagedMemoryRequest,
    candidates_for_session,
    records_for_session,
    require_memory_write,
    resolve_session_scope,
)
from .models import MemoryCandidate, MemoryCategory, MemoryRecord, MemoryScope
from .repository import MemoryConflictError, MemoryNotFoundError
from .service import MemoryPolicyError, MemoryService, default_memory_service


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def _translate_memory_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotFoundError):
        return _not_found("memory entity not found")
    if isinstance(exc, MemoryConflictError):
        return HTTPException(status_code=409, detail={"code": "memory_revision_conflict", "message": str(exc)})
    if isinstance(exc, MemoryPolicyError):
        return HTTPException(status_code=403, detail={"code": "memory_policy_rejected", "message": str(exc)})
    return HTTPException(status_code=400, detail=str(exc))


def register_memory_management_routes(
    app: FastAPI,
    *,
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
    memory_service_factory: Callable[[], MemoryService] = default_memory_service,
) -> None:
    names = {getattr(route, "name", "") for route in app.routes}

    def write_context(session_id: str):
        session, context = resolve_session_scope(chat_store_factory(), session_id)
        if session is None or context is None:
            raise _not_found("chat session not found")
        try:
            require_memory_write(session)
        except Exception as exc:
            raise _translate_memory_error(exc) from exc
        return context

    if "assistant_memory_list_endpoint" not in names:

        @app.get(
            "/api/assistant/memory",
            response_model=MemoryListResponse,
            include_in_schema=False,
            name="assistant_memory_list_endpoint",
        )
        async def assistant_memory_list_endpoint(
            session_id: str,
            scope: MemoryScope | None = None,
            category: MemoryCategory | None = None,
            pinned_only: bool = False,
            query: str | None = None,
            limit: int = Query(default=100, ge=0, le=500),
            offset: int = Query(default=0, ge=0),
        ) -> MemoryListResponse:
            result = records_for_session(
                chat_store_factory(),
                memory_service_factory(),
                session_id,
                scope=scope,
                category=category,
                pinned_only=pinned_only,
                query=query,
                limit=limit,
                offset=offset,
            )
            if result is None:
                raise _not_found("chat session not found")
            return result

        @app.post(
            "/api/assistant/memory",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_create_endpoint",
        )
        async def assistant_memory_create_endpoint(request: CreateManagedMemoryRequest) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().create_explicit_memory(
                    context,
                    scope=request.scope,
                    category=request.category,
                    content=request.content,
                    provenance_id=request.session_id,
                    pinned=request.pinned,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.get(
            "/api/assistant/memory/{memory_id}",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_read_endpoint",
        )
        async def assistant_memory_read_endpoint(memory_id: str, session_id: str) -> MemoryRecord:
            result = records_for_session(
                chat_store_factory(),
                memory_service_factory(),
                session_id,
                limit=500,
            )
            if result is None:
                raise _not_found("chat session not found")
            record = next((item for item in result.records if item.id == memory_id), None)
            if record is None:
                raise _not_found("memory record not found")
            return record

        @app.patch(
            "/api/assistant/memory/{memory_id}",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_update_endpoint",
        )
        async def assistant_memory_update_endpoint(
            memory_id: str,
            request: UpdateManagedMemoryRequest,
        ) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().edit_memory(
                    context,
                    memory_id,
                    content=request.content,
                    expected_revision=request.expected_revision,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.delete(
            "/api/assistant/memory/{memory_id}",
            response_model=ForgetMemoryResponse,
            include_in_schema=False,
            name="assistant_memory_forget_endpoint",
        )
        async def assistant_memory_forget_endpoint(
            memory_id: str,
            session_id: str,
            expected_revision: int = Query(ge=1),
        ) -> ForgetMemoryResponse:
            context = write_context(session_id)
            try:
                memory_service_factory().forget_memory(
                    context,
                    memory_id,
                    expected_revision=expected_revision,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc
            return ForgetMemoryResponse(memory_id=memory_id)

        @app.post(
            "/api/assistant/memory/{memory_id}/pin",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_pin_endpoint",
        )
        async def assistant_memory_pin_endpoint(
            memory_id: str,
            request: RevisionedMemoryRequest,
        ) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().set_pinned(
                    context,
                    memory_id,
                    pinned=True,
                    expected_revision=request.expected_revision,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.post(
            "/api/assistant/memory/{memory_id}/unpin",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_unpin_endpoint",
        )
        async def assistant_memory_unpin_endpoint(
            memory_id: str,
            request: RevisionedMemoryRequest,
        ) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().set_pinned(
                    context,
                    memory_id,
                    pinned=False,
                    expected_revision=request.expected_revision,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.post(
            "/api/assistant/memory/{memory_id}/move",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_move_endpoint",
        )
        async def assistant_memory_move_endpoint(
            memory_id: str,
            request: MoveManagedMemoryRequest,
        ) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().move_memory(
                    context,
                    memory_id,
                    target_scope=request.target_scope,
                    expected_revision=request.expected_revision,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.get(
            "/api/assistant/memory/candidates/pending",
            response_model=MemoryCandidateListResponse,
            include_in_schema=False,
            name="assistant_memory_candidates_endpoint",
        )
        async def assistant_memory_candidates_endpoint(
            session_id: str,
            limit: int = Query(default=100, ge=0, le=500),
        ) -> MemoryCandidateListResponse:
            result = candidates_for_session(
                chat_store_factory(),
                memory_service_factory(),
                session_id,
                limit=limit,
            )
            if result is None:
                raise _not_found("chat session not found")
            return result

        @app.post(
            "/api/assistant/memory/candidates/{candidate_id}/approve",
            response_model=MemoryRecord,
            include_in_schema=False,
            name="assistant_memory_candidate_approve_endpoint",
        )
        async def assistant_memory_candidate_approve_endpoint(
            candidate_id: str,
            request: CandidateResolutionRequest,
        ) -> MemoryRecord:
            context = write_context(request.session_id)
            try:
                return memory_service_factory().approve_candidate(
                    context,
                    candidate_id,
                    pinned=request.pinned,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.post(
            "/api/assistant/memory/candidates/{candidate_id}/reject",
            response_model=MemoryCandidate,
            include_in_schema=False,
            name="assistant_memory_candidate_reject_endpoint",
        )
        async def assistant_memory_candidate_reject_endpoint(
            candidate_id: str,
            request: CandidateResolutionRequest,
        ) -> MemoryCandidate:
            write_context(request.session_id)
            candidate = memory_service_factory().repository.get_candidate(candidate_id)
            if candidate is None:
                raise _not_found("memory candidate not found")
            visible = candidates_for_session(
                chat_store_factory(),
                memory_service_factory(),
                request.session_id,
                limit=500,
            )
            if visible is None or not any(item.id == candidate_id for item in visible.candidates):
                raise HTTPException(status_code=403, detail={"code": "candidate_scope_mismatch"})
            try:
                return memory_service_factory().reject_candidate(candidate_id)
            except Exception as exc:
                raise _translate_memory_error(exc) from exc

        @app.delete(
            "/api/assistant/memory/candidates/{candidate_id}",
            response_model=ForgetCandidateResponse,
            include_in_schema=False,
            name="assistant_memory_candidate_forget_endpoint",
        )
        async def assistant_memory_candidate_forget_endpoint(
            candidate_id: str,
            request: CandidateCleanupRequest,
        ) -> ForgetCandidateResponse:
            context = write_context(request.session_id)
            try:
                memory_service_factory().delete_resolved_candidate(
                    context,
                    candidate_id,
                    expected_status=request.expected_status,
                )
            except Exception as exc:
                raise _translate_memory_error(exc) from exc
            return ForgetCandidateResponse(candidate_id=candidate_id)
