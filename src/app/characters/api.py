"""FastAPI management routes for durable Character profiles and session mode."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from app.chat.models import ChatSession

from .live_call import CharacterLiveCallRuntime, resolve_live_call_runtime
from .management import (
    CharacterDataActionRequest,
    CharacterDataActionResponse,
    CharacterDataExport,
    CharacterManagementService,
)
from .models import (
    ArchiveCharacterResponse,
    CharacterListResponse,
    CharacterProfile,
    CharacterVersionListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from .repository import CharacterConflictError, CharacterNotFoundError
from .service import CharacterService, CharacterVoiceAssetError, default_character_service
from .session_models import SetSessionInteractionRequest


def register_character_routes(
    app: FastAPI,
    *,
    service_factory: Callable[[], CharacterService] = default_character_service,
    chat_store_factory: Callable[[], Any] | None = None,
) -> None:
    """Register typed routes while keeping the flagged feature out of public OpenAPI."""

    @app.get("/api/characters", response_model=CharacterListResponse, tags=["characters"], include_in_schema=False)
    async def list_characters(include_archived: bool = Query(default=False)) -> CharacterListResponse:
        return service_factory().list(include_archived=include_archived)

    @app.post("/api/characters", response_model=CharacterProfile, status_code=201, tags=["characters"], include_in_schema=False)
    async def create_character(request: CreateCharacterRequest) -> CharacterProfile:
        try:
            return service_factory().create(request)
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"], include_in_schema=False)
    async def get_character(character_id: str, include_archived: bool = Query(default=False)) -> CharacterProfile:
        try:
            return service_factory().get(character_id, include_archived=include_archived)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.patch("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"], include_in_schema=False)
    async def update_character(character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        try:
            return service_factory().update(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/characters/{character_id}", response_model=ArchiveCharacterResponse, tags=["characters"], include_in_schema=False)
    async def archive_character(character_id: str) -> ArchiveCharacterResponse:
        try:
            return service_factory().archive(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.get("/api/characters/{character_id}/versions", response_model=CharacterVersionListResponse, tags=["characters"], include_in_schema=False)
    async def list_character_versions(character_id: str) -> CharacterVersionListResponse:
        try:
            return service_factory().versions(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    if chat_store_factory is None:
        return

    def management_service() -> CharacterManagementService:
        return CharacterManagementService(service_factory(), chat_store_factory())

    @app.get(
        "/api/characters/{character_id}/data",
        response_model=CharacterDataExport,
        tags=["characters"],
        include_in_schema=False,
    )
    async def export_character_data(character_id: str) -> CharacterDataExport:
        try:
            return management_service().export(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.post(
        "/api/characters/{character_id}/data/actions",
        response_model=CharacterDataActionResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def apply_character_data_actions(
        character_id: str,
        request: CharacterDataActionRequest,
    ) -> CharacterDataActionResponse:
        try:
            return management_service().apply(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except (CharacterConflictError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"], include_in_schema=False)
    async def get_session_interaction(session_id: str) -> ChatSession:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @app.post("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"], include_in_schema=False)
    async def set_session_interaction(session_id: str, request: SetSessionInteractionRequest) -> ChatSession:
        try:
            session = chat_store_factory().set_session_interaction(session_id, request)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @app.get(
        "/api/chat/sessions/{session_id}/live-call/runtime",
        response_model=CharacterLiveCallRuntime,
        tags=["characters"],
        include_in_schema=False,
    )
    async def get_live_call_runtime(session_id: str) -> CharacterLiveCallRuntime:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        try:
            return resolve_live_call_runtime(session, character_service_factory=service_factory)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["register_character_routes"]
