"""Assistant-memory feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule

from .routes import register_assistant_memory_routes


def _router(_context: FeatureContext) -> APIRouter:
    router = APIRouter()
    register_assistant_memory_routes(router)  # type: ignore[arg-type]
    return router


FEATURE = FeatureModule(
    id="assistant-memory",
    title="Assistant Memory",
    depends_on=("chat",),
    routers=(_router,),
)
