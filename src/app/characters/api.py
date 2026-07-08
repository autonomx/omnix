"""FastAPI management routes for durable Character profiles."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

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


def register_character_routes(
    app: FastAPI,
    *,
    service_factory: Callable[[], CharacterService] = default_character_service,
) -> None:
    @app.get("/api/characters", response_model=CharacterListResponse, tags=["characters"])
    async def list_characters(
        include_archived: bool = Query(default=False),
    ) -> CharacterListResponse:
        return service_factory().list(include_archived=include_archived)

    @app.post("/api/characters", response_model=CharacterProfile, status_code=201, tags=["characters"])
    async def create_character(request: CreateCharacterRequest) -> CharacterProfile:
        try:
            return service_factory().create(request)
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"])
    async def get_character(
        character_id: str,
        include_archived: bool = Query(default=False),
    ) -> CharacterProfile:
        try:
            return service_factory().get(character_id, include_archived=include_archived)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.patch("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"])
    async def update_character(
        character_id: str,
        request: UpdateCharacterRequest,
    ) -> CharacterProfile:
        try:
            return service_factory().update(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete(
        "/api/characters/{character_id}",
        response_model=ArchiveCharacterResponse,
        tags=["characters"],
    )
    async def archive_character(character_id: str) -> ArchiveCharacterResponse:
        try:
            return service_factory().archive(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.get(
        "/api/characters/{character_id}/versions",
        response_model=CharacterVersionListResponse,
        tags=["characters"],
    )
    async def list_character_versions(character_id: str) -> CharacterVersionListResponse:
        try:
            return service_factory().versions(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc


__all__ = ["register_character_routes"]
