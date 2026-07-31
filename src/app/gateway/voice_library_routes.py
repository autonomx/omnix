"""Direct browser route for canonical local voice-clone profiles."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Response

from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets
from app.assets.models import AssetListResponse

_ROUTE_SENTINEL = "_omnix_voice_library_route_registered"
_HOOK_SENTINEL = "_omnix_voice_library_route_hook_installed"
VOICE_LIBRARY_PATH = "/api/voice-library"


def register_voice_library_route(gateway: FastAPI) -> None:
    """Register an uncapped endpoint backed directly by resources/voice_clones."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get(
        VOICE_LIBRARY_PATH,
        response_model=AssetListResponse,
        include_in_schema=False,
    )
    def voice_library(response: Response) -> AssetListResponse:
        assets = discover_canonical_voice_clone_assets()
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Omnix-Voice-Profile-Count"] = str(len(assets))
        response.headers["X-Omnix-Voice-Library-Source"] = "resources/voice_clones"
        return AssetListResponse(assets=assets)


def install_voice_library_route_hook() -> None:
    """Install the direct Voice Library route before gateway construction."""

    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_voice_library_route(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
