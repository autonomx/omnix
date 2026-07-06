"""Runtime gateway composition used by the local launcher."""
from __future__ import annotations

from app.gateway.image_model_routes import router as image_model_router
from app.gateway.main import app

app.include_router(image_model_router)

__all__ = ["app"]
