"""OpenAPI compatibility helpers for provisional assistant routes."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI

_PROVISIONAL_PREFIXES = ("/api/assistant/", "/api/hermes/assistant/")
_ORIGINAL_OPENAPI: Callable[[FastAPI], dict[str, Any]] | None = None
_ORIGINAL_INIT: Callable[..., None] | None = None


def install_assistant_tools_openapi_filter() -> None:
    """Install provisional assistant route hooks.

    Assistant tool routes are runtime surfaces first. They stay out of generated
    OpenAPI drift checks until the frontend generated contract intentionally owns
    them, while still being registered on gateway FastAPI instances.
    """

    _install_openapi_filter()
    _install_route_registrar()


def _install_openapi_filter() -> None:
    global _ORIGINAL_OPENAPI
    if _ORIGINAL_OPENAPI is not None:
        return

    _ORIGINAL_OPENAPI = FastAPI.openapi

    def filtered_openapi(self: FastAPI) -> dict[str, Any]:
        schema = _ORIGINAL_OPENAPI(self)
        paths = schema.get("paths")
        if isinstance(paths, dict):
            for path in list(paths):
                if path.startswith(_PROVISIONAL_PREFIXES):
                    paths.pop(path, None)
        return schema

    FastAPI.openapi = filtered_openapi


def _install_route_registrar() -> None:
    global _ORIGINAL_INIT
    if _ORIGINAL_INIT is not None:
        return

    _ORIGINAL_INIT = FastAPI.__init__

    def assistant_tools_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        _ORIGINAL_INIT(self, *args, **kwargs)
        from .routes import register_assistant_tool_routes

        register_assistant_tool_routes(self)

    FastAPI.__init__ = assistant_tools_init
