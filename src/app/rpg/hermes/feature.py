"""The Hermes feature: RPG planning, approved sequences and the sidecar routes (depends on RPG)."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule

from app.rpg.hermes.api import router as hermes_router
from app.rpg.hermes.approved_routes import hermes_rpg_approved_bp


def _router(_context: FeatureContext) -> APIRouter:
    router = APIRouter()
    router.include_router(hermes_router)
    router.include_router(hermes_rpg_approved_bp)
    return router


FEATURE = FeatureModule(
    id="hermes",
    title="Hermes",
    depends_on=("rpg",),
    routers=(_router,),
)
