"""Assistant-memory feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.runtime.features import FeatureContext, FeatureModule

from .routes import register_assistant_memory_routes


def _router(context: FeatureContext) -> APIRouter:
    router = APIRouter()
    kwargs = {}
    if context.services is not None and getattr(context.services, "chat", None) is not None:
        kwargs["chat_store_factory"] = lambda: context.services.chat
    register_assistant_memory_routes(router, **kwargs)  # type: ignore[arg-type]
    return router


FEATURE = FeatureModule(
    id="assistant-memory",
    title="Assistant Memory",
    depends_on=("chat",),
    routers=(_router,),
)
