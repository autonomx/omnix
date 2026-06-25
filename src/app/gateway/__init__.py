"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from typing import Any

from .rpg_session_routes import install_rpg_session_route_hook
from .rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook

__all__ = ["app", "create_gateway_app"]

install_rpg_session_route_hook()
install_rpg_turn_job_mirror_hook()


def __getattr__(name: str) -> Any:
    """Load the gateway app lazily to keep lightweight submodule imports safe."""
    if name in __all__:
        from .main import app, create_gateway_app

        return {"app": app, "create_gateway_app": create_gateway_app}[name]
    raise AttributeError(name)
