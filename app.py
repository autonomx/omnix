"""
LM Studio Chatbot - Flask Backend
Modular version using Blueprints
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from flask import Flask

# Import Blueprints
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

def create_app():
    # Force Flask to look for templates and static files in the src directory
    app = Flask(__name__, template_folder='src/templates', static_folder='src/static')
    
    # Pre-load TTS provider on app startup for immediate availability
    with app.app_context():
        try:
            import app.shared as shared
            # Force TTS provider initialization
            tts_provider = shared.get_tts_provider()
            if tts_provider:
                print(f"[APP-STARTUP] TTS provider '{tts_provider.provider_name}' initialized successfully")
            else:
                print("[APP-STARTUP] No TTS provider configured or available")
        except Exception as e:
            print(f"[APP-STARTUP] Failed to initialize TTS provider: {e}")
    
    # Register all Blueprints
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

if __name__ == '__main__':
    app = create_app()
    print("\n" + "=" * 50)
    print("Running with HTTP on http://0.0.0.0:5000")
    print("=" * 50 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)