from __future__ import annotations

from collections.abc import Callable
from inspect import signature
from typing import Any

from fastapi import APIRouter, FastAPI


def include_router_registrar(
    app: FastAPI,
    registrar: Callable[..., None],
    *args: Any,
    **kwargs: Any,
) -> None:
    router = APIRouter()
    if "state" in signature(registrar).parameters:
        kwargs.setdefault("state", app.state)
    registrar(router, *args, **kwargs)
    app.include_router(router)
