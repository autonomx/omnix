"""Gateway hook for assistant web and desktop context routes."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from app.assistant_context import register_assistant_context_routes
from app.research.credential_routes import register_research_credential_routes

_HOOK_SENTINEL = "_omnix_assistant_context_route_hook_installed"


def install_assistant_context_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_assistant_context_routes(self)
            register_research_credential_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)