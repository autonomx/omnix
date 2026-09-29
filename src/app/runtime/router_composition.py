"""Composition helpers that produce routers without handing features a FastAPI app."""
from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import APIRouter


class APIRouterHost:
    """Expose router registration methods together with explicit runtime state."""

    def __init__(self, router: APIRouter | None = None, *, state: Any = None) -> None:
        self.router = router or APIRouter()
        self.state = state

    def __getattr__(self, name: str) -> Any:
        return getattr(self.router, name)


def compose_registrar_router(
    registrars: tuple[tuple[str, str], ...],
    *,
    state: Any = None,
) -> APIRouter:
    """Compose transitional route modules into one owned APIRouter.

    A registrar receives only an APIRouterHost. Middleware and app lifecycle
    registration stay in the composition root and must use explicit kernel
    extension points.
    """

    host = APIRouterHost(state=state)
    for module_name, registrar_name in registrars:
        before = (len(host.router.on_startup), len(host.router.on_shutdown))
        registrar = getattr(import_module(module_name), registrar_name)
        registrar(host)
        after = (len(host.router.on_startup), len(host.router.on_shutdown))
        if before != after:
            raise RuntimeError(
                f"{module_name}.{registrar_name} must declare a FeatureLifecycle"
            )
    return host.router
