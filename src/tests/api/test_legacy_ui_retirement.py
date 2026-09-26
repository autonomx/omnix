"""Retired application servers cannot replace or leak into the shared gateway."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC_DIR))


def test_all_application_entrypoints_use_the_shared_gateway():
    import launch
    import main
    from app import create_app
    from app.gateway.main import app

    assert launch.create_app() is main.create_app() is app
    assert (launch.HOST, launch.PORT) == (main.HOST, main.PORT)
    factory_app = create_app()
    assert factory_app.title == "Omnix Web Gateway"
    response = TestClient(factory_app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "omnix-gateway"


def test_current_apps_keep_their_shared_contracts_without_old_routes():
    from app.gateway.main import create_gateway_app

    gateway = create_gateway_app()
    paths = {route.path for route in gateway.routes}
    assert {
        "/api/chat/sessions", "/api/jobs", "/api/assets",
        "/api/audiobook/projects", "/api/rpg/session/get",
        "/api/image-generation/assets", "/api/workers/health",
    } - paths == set()
    retired = {
        "/api/chat/stream", "/api/podcast/generate", "/api/story/generate",
        "/api/voice_studio/generate", "/api/voice_clone",
        "/api/rpg/games", "/generated-images/{filename:path}",
        "/ws/conversation", "/static",
    }
    assert paths.isdisjoint(retired)
    assert TestClient(gateway).get("/static/script.js").status_code == 404
