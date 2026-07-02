"""
Omnix application package.

All routes and application logic now use FastAPI exclusively.
Flask has been completely removed.

See root app.py for the main FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize providers on application startup"""
    try:
        from app.rpg.visual.runtime_status import log_flux_klein_runtime_status

        log_flux_klein_runtime_status()
    except Exception as e:
        print(f"[APP-STARTUP] Failed to validate FLUX runtime: {e}")

    yield


def _hermes_test_request(payload: dict[str, Any] | None):
    from app.assist_core.hermes_diagnostics import HermesDiagnosticsTestRequest

    data = payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return HermesDiagnosticsTestRequest(
        content=str(data.get("content") or "house status"),
        session_id=str(data.get("session_id") or "diagnostics"),
        domain=str(data.get("domain") or "chat"),
        metadata=dict(metadata),
    )


def create_fastapi_app() -> FastAPI:
    """Create and configure the complete FastAPI application with all routers."""
    from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_bp

    from .rpg.api.rpg_adventure_routes import rpg_adventure_bp
    from .rpg.api.rpg_debug_routes import rpg_debug_bp
    from .rpg.api.rpg_dialogue_routes import rpg_dialogue_bp
    from .rpg.api.rpg_encounter_routes import rpg_encounter_bp
    from .rpg.api.rpg_game_routes import rpg_game_bp
    from .rpg.api.rpg_inspection_routes import rpg_inspection_bp
    from .rpg.api.rpg_package_routes import rpg_package_bp
    from .rpg.api.rpg_player_routes import rpg_player_bp
    from .rpg.api.rpg_presentation_routes import rpg_presentation_bp
    from .rpg.api.rpg_session_routes import rpg_session_bp
    from .rpg.creator_routes import creator_bp

    app = FastAPI(
        title="Omnix API",
        lifespan=lifespan,
    )

    @app.get("/api/hermes/status")
    def hermes_status() -> dict[str, Any]:
        from app.assist_core.hermes_diagnostics import hermes_diagnostics_status_payload

        return hermes_diagnostics_status_payload()

    @app.post("/api/hermes/test")
    def hermes_test(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        from app.assist_core.hermes_diagnostics import hermes_diagnostics_test_payload

        return hermes_diagnostics_test_payload(_hermes_test_request(payload))

    # Register all FastAPI routers
    app.include_router(creator_bp)
    app.include_router(rpg_adventure_bp)
    app.include_router(rpg_game_bp)
    app.include_router(rpg_debug_bp)
    app.include_router(rpg_player_bp)
    app.include_router(rpg_dialogue_bp)
    app.include_router(rpg_encounter_bp)
    app.include_router(rpg_package_bp)
    app.include_router(rpg_inspection_bp)
    app.include_router(rpg_session_bp)
    app.include_router(rpg_presentation_bp)
    app.include_router(hermes_rpg_approved_bp)

    return app


# Legacy alias - kept for backwards compatibility with tests
create_app = create_fastapi_app
