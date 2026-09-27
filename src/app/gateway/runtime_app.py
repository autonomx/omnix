"""Runtime gateway composition used by the local launcher."""
from __future__ import annotations

from app.production import ProductionApplication, create_production_app


def create_runtime_app():
    from app.gateway.image_model_routes import router as image_model_router
    from app.gateway.live_job_events import install_resilient_live_job_events

    gateway = create_production_app()
    install_resilient_live_job_events(
        gateway, job_store_factory=lambda: gateway.state.runtime_services.jobs
    )
    gateway.include_router(image_model_router)
    return gateway


app = ProductionApplication(factory=create_runtime_app)

__all__ = ["app"]
