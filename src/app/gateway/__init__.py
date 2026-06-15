"""Thin FastAPI gateway foundation for the Omnix web app redesign."""
from __future__ import annotations

from .main import app, create_gateway_app

__all__ = ["app", "create_gateway_app"]
