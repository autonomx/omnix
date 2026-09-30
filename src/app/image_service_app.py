"""ASGI entrypoint retained for existing launcher configurations."""
from __future__ import annotations

from .image_service_runtime import app

__all__ = ["app"]
