"""Characters feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule

from .api import register_character_routes
from .avatar_api import register_character_avatar_routes
from .avatar_generation_api import register_character_avatar_generation_routes
from .avatar_viseme_api import register_character_avatar_viseme_routes


def _router(_context: FeatureContext) -> APIRouter:
    router = APIRouter()
    register_character_routes(router)  # type: ignore[arg-type]
    register_character_avatar_routes(router)  # type: ignore[arg-type]
    register_character_avatar_generation_routes(router)  # type: ignore[arg-type]
    register_character_avatar_viseme_routes(router)  # type: ignore[arg-type]
    return router


FEATURE = FeatureModule(
    id="characters",
    title="Characters",
    depends_on=("chat", "assistant-memory", "companion-activity"),
    routers=(_router,),
)
