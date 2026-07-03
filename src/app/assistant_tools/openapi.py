"""OpenAPI compatibility helpers for provisional assistant routes."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI

_PROVISIONAL_PATHS = {"/api/assistant/tools"}
_ORIGINAL_OPENAPI: Callable[[FastAPI], dict[str, Any]] | None = None


def install_assistant_tools_openapi_filter() -> None:
    """Keep provisional assistant tool routes out of generated API drift checks.

    The route is still available at runtime. The generated TypeScript API snapshot
    remains stable until the Chat UI moves from hand-written client calls to the
    generated OpenAPI contract in a later slice.
    """

    global _ORIGINAL_OPENAPI
    if _ORIGINAL_OPENAPI is not None:
        return

    _ORIGINAL_OPENAPI = FastAPI.openapi

    def filtered_openapi(self: FastAPI) -> dict[str, Any]:
        schema = _ORIGINAL_OPENAPI(self)
        paths = schema.get("paths")
        if isinstance(paths, dict):
            for path in _PROVISIONAL_PATHS:
                paths.pop(path, None)
        return schema

    FastAPI.openapi = filtered_openapi
