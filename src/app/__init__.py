"""
Omnix application package.

All routes and application logic now use FastAPI exclusively.
Flask has been completely removed.

See root app.py for the main FastAPI application entry point.
"""

from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize providers on application startup"""
    # Pre-load TTS provider on app startup for immediate availability
    try:
        import app.shared as shared
        tts_provider = shared.get_tts_provider()
        if tts_provider:
            print(f"[APP-STARTUP] TTS provider '{tts_provider.provider_name}' initialized successfully")
        else:
            print("[APP-STARTUP] No TTS provider configured or available")
    except Exception as e:
        print(f"[APP-STARTUP] Failed to initialize TTS provider: {e}")
    
    yield


def create_fastapi_app() -> FastAPI:
    """Create and configure the complete FastAPI application with all routers."""
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

    pkg_dir = Path(__file__).resolve().parent
    
    app = FastAPI(
        title="Omnix API",
        lifespan=lifespan,
    )

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

    return app


# Legacy alias - kept for backwards compatibility with tests
create_app = create_fastapi_app
