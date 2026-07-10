"""FastAPI routes for Character avatar generation and governed voice backfill."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .avatar_generation_models import (
    BackfillClonedVoiceCharactersRequest,
    BackfillClonedVoiceCharactersResponse,
    CharacterAvatarGenerationBatch,
    CharacterAvatarGenerationListResponse,
    CreateCharacterAvatarGenerationRequest,
)
from .avatar_generation_service import (
    CharacterAvatarGenerationNotFoundError,
    CharacterAvatarGenerationService,
    default_character_avatar_generation_service,
)
from .repository import CharacterNotFoundError


def register_character_avatar_generation_routes(
    app: FastAPI,
    *,
    service_factory: Callable[
        [], CharacterAvatarGenerationService
    ] = default_character_avatar_generation_service,
) -> None:
    @app.post(
        "/api/characters/{character_id}/avatar-generations",
        response_model=CharacterAvatarGenerationBatch,
        status_code=202,
        tags=["characters"],
        include_in_schema=False,
    )
    async def create_character_avatar_generation(
        character_id: str,
        request: CreateCharacterAvatarGenerationRequest,
    ) -> CharacterAvatarGenerationBatch:
        try:
            return service_factory().create(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/characters/{character_id}/avatar-generations",
        response_model=CharacterAvatarGenerationListResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def list_character_avatar_generations(
        character_id: str,
    ) -> CharacterAvatarGenerationListResponse:
        try:
            return service_factory().list(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.get(
        "/api/character-avatar-generations/{batch_id}",
        response_model=CharacterAvatarGenerationBatch,
        tags=["characters"],
        include_in_schema=False,
    )
    async def get_character_avatar_generation(
        batch_id: str,
    ) -> CharacterAvatarGenerationBatch:
        try:
            return service_factory().get(batch_id)
        except CharacterAvatarGenerationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="avatar generation not found") from exc

    @app.post(
        "/api/characters/backfill-cloned-voices",
        response_model=BackfillClonedVoiceCharactersResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def backfill_cloned_voice_characters(
        request: BackfillClonedVoiceCharactersRequest,
    ) -> BackfillClonedVoiceCharactersResponse:
        return service_factory().backfill_cloned_voices(request)


__all__ = ["register_character_avatar_generation_routes"]
