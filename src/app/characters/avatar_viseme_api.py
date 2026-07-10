"""FastAPI routes for expanded Character avatar viseme generation."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .avatar_viseme_generation import (
    CharacterVisemeGenerationBatch,
    CharacterVisemeGenerationService,
)
from .repository import CharacterNotFoundError


def register_character_avatar_viseme_routes(
    app: FastAPI,
    *,
    service_factory: Callable[[], CharacterVisemeGenerationService] = CharacterVisemeGenerationService,
) -> None:
    @app.post(
        "/api/characters/{character_id}/avatar-visemes",
        response_model=CharacterVisemeGenerationBatch,
        status_code=202,
        tags=["characters"],
        include_in_schema=False,
    )
    async def create_character_avatar_visemes(character_id: str) -> CharacterVisemeGenerationBatch:
        try:
            return service_factory().create(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character or avatar pack not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/character-avatar-visemes/{batch_id}",
        response_model=CharacterVisemeGenerationBatch,
        tags=["characters"],
        include_in_schema=False,
    )
    async def get_character_avatar_visemes(batch_id: str) -> CharacterVisemeGenerationBatch:
        try:
            return service_factory().get(batch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="viseme generation not found") from exc


__all__ = ["register_character_avatar_viseme_routes"]
