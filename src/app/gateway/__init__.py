"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from typing import Any

import app.jobs
from .rpg_direct_turn_routes import install_direct_turn_hook
from .rpg_session_routes import install_rpg_session_route_hook

__all__ = ["app", "create_gateway_app"]

install_rpg_session_route_hook()
install_direct_turn_hook()


def __getattr__(name: str) -> Any:
    """Load the gateway app lazily to keep lightweight submodule imports safe."""
    if name in __all__:
        from .main import app, create_gateway_app

        return {"app": app, "create_gateway_app": create_gateway_app}[name]
    raise AttributeError(name)
