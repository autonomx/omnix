"""Compatibility registrar for Hermes routers.

Production composition uses app.assist_core.feature directly.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.assist_core.hermes_api import router as hermes_router
from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_bp


def register_hermes_routes(app: FastAPI) -> None:
    app.include_router(hermes_router)
    app.include_router(hermes_rpg_approved_bp, include_in_schema=False)


__all__ = ["register_hermes_routes"]
