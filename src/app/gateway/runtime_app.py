"""Runtime gateway composition used by the local launcher."""
from __future__ import annotations

from app.gateway.image_model_routes import router as image_model_router
from app.gateway.live_job_events import install_resilient_live_job_events
from app.gateway.main import app

install_resilient_live_job_events(app)
app.include_router(image_model_router)

__all__ = ["app"]
