"""
Omnix application package.

Provides ``create_app`` so that other code (tests, WSGI servers) can build a
fully-configured Flask application without reaching for the root ``app.py``.
"""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application with all blueprints."""
    from app.core import core_bp
    from app.chat import chat_bp
    from app.services import services_bp
    from app.audio import audio_bp
    from app.audiobook import audiobook_bp
    from app.podcast import podcast_bp
    from app.llm import llm_bp
    from app.llamacpp import llamacpp_bp
    from app.voice_studio import voice_studio_bp
    from app.rpg.routes import rpg_bp

    app = Flask(
        __name__,
        template_folder=str(__import__("pathlib").Path(__file__).resolve().parent.parent / "templates"),
        static_folder=str(__import__("pathlib").Path(__file__).resolve().parent.parent / "static"),
    )

    # Pre-load TTS provider on app startup for immediate availability
    with app.app_context():
        try:
            import app.shared as shared
            tts_provider = shared.get_tts_provider()
            if tts_provider:
                print(f"[APP-STARTUP] TTS provider '{tts_provider.provider_name}' initialized successfully")
            else:
                print("[APP-STARTUP] No TTS provider configured or available")
        except Exception as e:
            print(f"[APP-STARTUP] Failed to initialize TTS provider: {e}")

    app.register_blueprint(core_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(audiobook_bp)
    app.register_blueprint(podcast_bp)
    app.register_blueprint(llm_bp)
    app.register_blueprint(llamacpp_bp)
    app.register_blueprint(voice_studio_bp)
    app.register_blueprint(rpg_bp)

    return app
