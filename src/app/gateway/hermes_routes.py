"""Hermes gateway route installer."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.assist_core.hermes_api import router as hermes_router

_ROUTE_SENTINEL = "_omnix_hermes_routes_registered"
_HOOK_SENTINEL = "_omnix_hermes_route_hook_installed"


def register_hermes_routes(app: FastAPI) -> None:
    """Attach Hermes status and test routes to the web gateway once."""
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    app.include_router(hermes_router)
    setattr(app.state, _ROUTE_SENTINEL, True)


def install_hermes_route_hook() -> None:
    """Install Hermes routes when the local gateway app is created."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_hermes_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
