"""Trading route hook for the shared Omnix gateway."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.trading.api import create_trading_router

_ROUTE_SENTINEL = "_omnix_trading_routes_registered"
_HOOK_SENTINEL = "_omnix_trading_route_hook_installed"


def register_trading_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    gateway.include_router(create_trading_router())
    setattr(gateway.state, _ROUTE_SENTINEL, True)


def install_trading_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_trading_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
