"""Contract tests proving the classic browser UI is retired."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from run_app import app

    return TestClient(app, raise_server_exceptions=False)


def _classify_run_app_route(path: str) -> str | None:
    exact = {
        "/": "backend-status",
        "/health": "backend-status",
        "/api/health": "backend-status",
        "/api/runtime/status": "backend-status",
        "/api/services/status": "backend-status",
        "/generated-images/{filename:path}": "runtime-data",
        "/api/settings": "legacy-settings",
        "/api/models": "legacy-provider-models",
        "/api/clear": "legacy-chat-control",
        "/api/voice_clones": "legacy-voice",
        "/api/voice_clones/{voice_id}": "legacy-voice",
        "/api/voice_clone": "legacy-voice",
        "/api/voice_studio/generate": "legacy-voice",
        "/api/voice_studio/voices": "legacy-voice",
        "/docs": "framework-docs",
        "/docs/oauth2-redirect": "framework-docs",
        "/redoc": "framework-docs",
        "/openapi.json": "framework-docs",
    }
    if path in exact:
        return exact[path]

    prefixes = [
        ("/api/sessions", "legacy-sessions"),
        ("/api/rpg", "legacy-rpg"),
        ("/setup-flow", "legacy-rpg"),
        ("/session-bootstrap", "legacy-rpg"),
        ("/intro-scene", "legacy-rpg"),
        ("/save-load-ux", "legacy-rpg"),
        ("/narrative-recap", "legacy-rpg"),
        ("/api/image", "legacy-image"),
        ("/api/tts", "legacy-voice"),
        ("/api/stt", "legacy-voice"),
        ("/api/voice", "legacy-voice"),
        ("/ws/conversation", "legacy-voice"),
        ("/ws/tts", "legacy-voice"),
        ("/api/podcast", "legacy-podcast-story-audiobook"),
        ("/api/story", "legacy-podcast-story-audiobook"),
        ("/api/audiobook", "legacy-podcast-story-audiobook"),
        ("/ws/audiobook", "legacy-podcast-story-audiobook"),
        ("/api/openrouter", "legacy-provider-models"),
        ("/api/providers", "legacy-provider-models"),
        ("/api/llm", "legacy-provider-models"),
        ("/api/llamacpp", "legacy-provider-models"),
        ("/api/chat", "legacy-chat-control"),
        ("/api/conversation", "legacy-chat-control"),
        ("/api/services/xtts/logs", "legacy-service-logs"),
        ("/api/services/stt/logs", "legacy-service-logs"),
    ]
    for prefix, classification in prefixes:
        if path == prefix or path.startswith(f"{prefix}/"):
            return classification
    return None


def _route_methods(route: Any) -> tuple[str, ...]:
    methods = getattr(route, "methods", None)
    if methods:
        return tuple(sorted(str(method) for method in methods))
    return ("WEBSOCKET",)


def test_run_app_root_is_backend_status_not_classic_html() -> None:
    response = _client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["ok"] is True
    assert payload["browser_ui"] == "src/apps/web"
    assert payload["gateway"] == "app.gateway.main:app"


def test_run_app_no_longer_serves_classic_static_files() -> None:
    response = _client().get("/static/script.js")

    assert response.status_code == 404


def test_run_app_generated_images_remain_data_surface(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()
    image = image_root / "scene.png"
    image.write_bytes(b"png")

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/scene.png")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == b"png"


def test_run_app_missing_generated_image_reports_diagnostic(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/missing.png")

    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "file_not_found"}


def test_run_app_rejects_generated_image_path_traversal(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/../secret.png")

    assert response.status_code in {400, 404}
    if response.status_code == 400:
        assert response.json() == {"ok": False, "error": "invalid_filename"}


def test_run_app_compatibility_routes_are_classified() -> None:
    from run_app import app

    unclassified = []
    classifications: dict[str, set[str]] = {}
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        classification = _classify_run_app_route(path)
        if classification is None:
            unclassified.append({"path": path, "methods": _route_methods(route)})
            continue
        classifications.setdefault(classification, set()).add(path)

    assert unclassified == []
    for required in [
        "backend-status",
        "runtime-data",
        "legacy-settings",
        "legacy-sessions",
        "legacy-rpg",
        "legacy-image",
        "legacy-voice",
        "legacy-podcast-story-audiobook",
        "legacy-provider-models",
        "legacy-chat-control",
        "legacy-service-logs",
    ]:
        assert required in classifications


def test_run_app_required_transition_routes_remain_mounted() -> None:
    from run_app import app

    route_methods: dict[str, set[str]] = {}
    for route in app.routes:
        route_methods.setdefault(str(getattr(route, "path", "")), set()).update(_route_methods(route))

    required_routes = {
        "/health": {"GET"},
        "/api/runtime/status": {"GET"},
        "/api/services/status": {"GET"},
        "/generated-images/{filename:path}": {"GET"},
        "/api/settings": {"GET", "POST"},
        "/api/sessions": {"GET", "POST"},
        "/api/sessions/{session_id}": {"GET", "PUT", "DELETE"},
        "/api/rpg/adventure/templates": {"GET"},
        "/api/rpg/session/list": {"POST"},
        "/api/rpg/player/state": {"POST"},
        "/api/image/generate": {"POST"},
        "/api/voice_clones": {"GET"},
        "/api/voice_clone": {"POST"},
        "/api/podcast/episodes": {"GET"},
        "/api/audiobook/library": {"GET"},
        "/api/models": {"GET"},
        "/api/chat/stream": {"POST"},
        "/api/services/xtts/logs": {"GET"},
    }

    missing = {
        path: sorted(methods - route_methods.get(path, set()))
        for path, methods in required_routes.items()
        if path not in route_methods or not methods.issubset(route_methods[path])
    }

    assert missing == {}
