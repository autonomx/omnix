"""Desktop companion feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule

from .routes import register_desktop_companion_routes


def _router(_context: FeatureContext) -> APIRouter:
    router = APIRouter()
    register_desktop_companion_routes(router)  # type: ignore[arg-type]
    return router


FEATURE = FeatureModule(
    id="desktop-companion",
    title="Desktop Companion",
    depends_on=("chat", "companion-activity"),
    routers=(_router,),
)
