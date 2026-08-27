"""Generalized agent runtime route registration."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

_ROUTE_SENTINEL = "_omnix_agent_runtime_routes_registered"
_HOOK_SENTINEL = "_omnix_agent_runtime_route_hook_installed"


def register_agent_runtime_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    from app.agent_runtime.api import router

    app.include_router(router)
    setattr(app.state, _ROUTE_SENTINEL, True)


def install_agent_runtime_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def wrapped_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_agent_runtime_routes(self)

    FastAPI.__init__ = wrapped_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
