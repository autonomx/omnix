"""Hermes gateway route registration."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.assist_core.hermes_api import router as hermes_router
from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_bp

_ROUTE_SENTINEL = "_omnix_hermes_routes_registered"
_HOOK_SENTINEL = "_omnix_hermes_route_hook_installed"


def register_hermes_routes(app: FastAPI) -> None:
    """Attach Hermes diagnostics and approved RPG workflow routes once."""
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)
    app.include_router(hermes_router)
    # Approved workflow endpoints are internal orchestration surfaces. Keep them
    # callable without expanding the public generated client contract.
    app.include_router(hermes_rpg_approved_bp, include_in_schema=False)


def install_hermes_route_hook() -> None:
    """Install Hermes routes for newly created Omnix gateway apps."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def wrapped_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_hermes_routes(self)

    FastAPI.__init__ = wrapped_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
