"""Characters feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.persistence.repository_registry import RepositorySpec
from app.runtime.features import FeatureContext, FeatureModule
from app.characters.persistence.repository import PostgresCharacterRepository

from .api import register_character_routes
from .avatar_api import register_character_avatar_routes
from .avatar_generation_api import register_character_avatar_generation_routes
from .avatar_viseme_api import register_character_avatar_viseme_routes
from .live2d_avatar import register_character_live2d_avatar_routes
from .live_conversation_rendering import register_live_conversation_rendering_routes


def _router(context: FeatureContext) -> APIRouter:
    router = APIRouter()
    chat_kwargs = {}
    if context.services is not None and getattr(context.services, "chat", None) is not None:
        chat_kwargs["chat_store_factory"] = lambda: context.services.chat
    register_character_routes(router, **chat_kwargs)  # type: ignore[arg-type]
    register_character_avatar_routes(router)  # type: ignore[arg-type]
    register_character_avatar_generation_routes(router)  # type: ignore[arg-type]
    register_character_avatar_viseme_routes(router)  # type: ignore[arg-type]
    register_character_live2d_avatar_routes(router)  # type: ignore[arg-type]
    register_live_conversation_rendering_routes(router, **chat_kwargs)  # type: ignore[arg-type]
    return router


FEATURE = FeatureModule(
    id="characters",
    title="Characters",
    depends_on=("chat", "assistant-memory", "companion-activity"),
    routers=(_router,),
    repositories=(RepositorySpec(PostgresCharacterRepository, PostgresCharacterRepository, "characters"),),
)
